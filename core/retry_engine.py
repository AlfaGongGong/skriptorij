"""
BooklyFi — retry_engine.py
Korak 8: Auto-retry loših blokova

Problem: blokovi ispod 7.5 ostaju loši, samo se loguju u human_review.json
Rješenje: nakon svakog poglavlja retranslacija s drugim modelom,
          uzima max(original_score, retry_score), limit 2 retry po bloku
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konfiguracija praga po žanru
# ---------------------------------------------------------------------------

RETRY_THRESHOLDS = {
    "default":    7.5,
    "sf":         7.2,   # SF može imati niži prag (neologizmi, imena)
    "fantasy":    7.2,
    "književnost": 7.8,  # Književnost traži viši standard
    "misterij":   7.4,
    "triler":     7.4,
}

MAX_RETRY_PER_BLOCK = 2   # Max pokušaja po bloku
RETRY_DELAY_SEC     = 1.5 # Pauza između retry-a (rate limit zaštita)


# ---------------------------------------------------------------------------
# Dataclass za retry rezultat
# ---------------------------------------------------------------------------

@dataclass
class RetryResult:
    chunk_id: str
    original_score: float
    retry_score: float
    final_score: float
    used_model: str
    retry_count: int
    improved: bool
    final_text: str


# ---------------------------------------------------------------------------
# Glavni RetryEngine
# ---------------------------------------------------------------------------

class RetryEngine:
    """
    Nakon svakog poglavlja čita quality_scores, pronalazi blokove
    ispod praga i retranslira ih s drugim modelom.
    """

    def __init__(
        self,
        translator_fn,          # callable(text, model) -> (str, float)
        scorer_fn,              # callable(original, translation, model) -> float
        model_selector_fn,      # callable(exclude_model) -> str
        genre: str = "default",
        logs_dir: str = "logs",
    ):
        self.translate    = translator_fn
        self.score        = scorer_fn
        self.select_model = model_selector_fn
        self.threshold    = RETRY_THRESHOLDS.get(genre, RETRY_THRESHOLDS["default"])
        self.logs_dir     = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Javno sučelje — poziva se iz workers.py
    # ------------------------------------------------------------------

    def process_chapter(
        self,
        chapter_id: str,
        chunks: list[dict],          # [{"id", "original", "translation", "score", "model"}]
        book_path: str,
    ) -> list[dict]:
        """
        Prima listu chunkova jednog poglavlja.
        Vraća istu listu s eventualnim poboljšanjima.
        """
        bad_chunks = [
            c for c in chunks
            if c.get("score", 10.0) < self.threshold
        ]

        if not bad_chunks:
            logger.info(f"[Retry] Poglavlje {chapter_id}: svi blokovi iznad praga {self.threshold}")
            return chunks

        logger.info(
            f"[Retry] Poglavlje {chapter_id}: {len(bad_chunks)} blok(ova) "
            f"ispod praga {self.threshold} → pokretanje retranslacije"
        )

        results: list[RetryResult] = []
        chunk_map = {c["id"]: c for c in chunks}

        for chunk in bad_chunks:
            result = self._retry_chunk(chunk)
            results.append(result)

            # Ažuriraj chunk_map s boljim prijevodom
            if result.improved:
                chunk_map[chunk["id"]]["translation"] = result.final_text
                chunk_map[chunk["id"]]["score"]       = result.final_score
                chunk_map[chunk["id"]]["model"]       = result.used_model
                chunk_map[chunk["id"]]["retried"]     = True

        self._log_retry_session(chapter_id, book_path, results)
        return list(chunk_map.values())

    # ------------------------------------------------------------------
    # Interni retry za jedan chunk
    # ------------------------------------------------------------------

    def _retry_chunk(self, chunk: dict) -> RetryResult:
        chunk_id       = chunk["id"]
        original_text  = chunk["original"]
        original_trans = chunk["translation"]
        original_score = chunk.get("score", 0.0)
        original_model = chunk.get("model", "unknown")

        best_text  = original_trans
        best_score = original_score
        best_model = original_model
        attempt    = 0

        while attempt < MAX_RETRY_PER_BLOCK and best_score < self.threshold:
            attempt += 1

            # Biramo drugi model (ne onaj koji je već prevodio)
            retry_model = self.select_model(exclude=best_model)
            logger.debug(
                f"[Retry] Chunk {chunk_id}, pokušaj {attempt}: "
                f"{original_model} → {retry_model}"
            )

            try:
                retry_trans = self.translate(original_text, retry_model)
                retry_score = self.score(
                    original_text,
                    retry_trans,
                    retry_model,   # scorer bira treći model
                )

                logger.debug(
                    f"[Retry] Chunk {chunk_id}: "
                    f"original={original_score:.2f}, retry={retry_score:.2f}"
                )

                # Uzimamo bolji rezultat
                if retry_score > best_score:
                    best_text  = retry_trans
                    best_score = retry_score
                    best_model = retry_model

            except Exception as e:
                logger.warning(f"[Retry] Chunk {chunk_id}, pokušaj {attempt} neuspješan: {e}")

            if attempt < MAX_RETRY_PER_BLOCK:
                time.sleep(RETRY_DELAY_SEC)

        improved = best_score > original_score

        if improved:
            logger.info(
                f"[Retry] ✅ Chunk {chunk_id}: "
                f"{original_score:.2f} → {best_score:.2f} (+{best_score - original_score:.2f})"
            )
        else:
            logger.info(
                f"[Retry] ⚠️  Chunk {chunk_id}: nije poboljšan "
                f"(ostaje {original_score:.2f})"
            )

        return RetryResult(
            chunk_id       = chunk_id,
            original_score = original_score,
            retry_score    = best_score,
            final_score    = best_score,
            used_model     = best_model,
            retry_count    = attempt,
            improved       = improved,
            final_text     = best_text,
        )

    # ------------------------------------------------------------------
    # Logiranje retry sesije
    # ------------------------------------------------------------------

    def _log_retry_session(
        self,
        chapter_id: str,
        book_path: str,
        results: list[RetryResult],
    ) -> None:
        log_entry = {
            "chapter_id":  chapter_id,
            "book":        book_path,
            "threshold":   self.threshold,
            "total":       len(results),
            "improved":    sum(1 for r in results if r.improved),
            "not_improved":sum(1 for r in results if not r.improved),
            "avg_gain":    (
                sum(r.final_score - r.original_score for r in results if r.improved)
                / max(1, sum(1 for r in results if r.improved))
            ),
            "details": [
                {
                    "chunk_id":       r.chunk_id,
                    "original_score": round(r.original_score, 3),
                    "final_score":    round(r.final_score, 3),
                    "gain":           round(r.final_score - r.original_score, 3),
                    "model":          r.used_model,
                    "retry_count":    r.retry_count,
                    "improved":       r.improved,
                }
                for r in results
            ],
        }

        log_file = self.logs_dir / "retry_log.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        logger.info(
            f"[Retry] Poglavlje {chapter_id}: "
            f"{log_entry['improved']}/{log_entry['total']} poboljšano, "
            f"prosj. dobitak: +{log_entry['avg_gain']:.2f}"
        )


# ---------------------------------------------------------------------------
# Integracija u workers.py — snippet za copy-paste
# ---------------------------------------------------------------------------
#
# Na kraju process_single_file_worker(), nakon chapter summary:
#
#   from core.retry_engine import RetryEngine
#
#   retry_engine = RetryEngine(
#       translator_fn  = lambda text, model: worker_v2.translate(text, model),
#       scorer_fn      = quality_scorer_v2.score_cross_provider,
#       model_selector_fn = provider_router_v2.select_alternative_model,
#       genre          = book_context.genre or "default",
#       logs_dir       = str(LOGS_DIR),
#   )
#
#   for chapter_id, chunks in chapter_chunks.items():
#       updated = retry_engine.process_chapter(chapter_id, chunks, book_path)
#       chapter_chunks[chapter_id] = updated
#
# ---------------------------------------------------------------------------
