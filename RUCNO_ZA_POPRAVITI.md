# Ručno za popraviti

Ovo skripta ne smije mijenjati bez da vidi namjeru koda. Zalijepi sadržaj (ili pojedine blokove) u chat i riješit ćemo.

## F841 — app.py:1684
Local variable `clean` is assigned to but never used
```python
    1679                      "output_file", ""
    1680                  )
    1681                  if book:
    1682                      import re as _re
    1683  
>>  1684                      clean = _re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
    1685                      # Koristi isti direktorij gdje je .chk fajl
    1686                      qs_dir = chk_path.parent
    1687                      qs_path = qs_dir / "quality_scores.json"
    1688  
    1689                      scores = {}
```

## PLE2510 — core/quality.py:350
Invalid unescaped character backspace, use "\b" instead
```python
     345      t = (tekst or "").strip()
     346      if not t:
     347          return True
     348  
     349      # 1. Čisto-slikovni blok
>>   350      if _re.search(r"^\s*<(img|figure|svg)<BACKSPACE>", t, _re.IGNORECASE):
     351          return True
     352      # Blok koji sadrži SAMO sliku (img bez okolnog teksta)
     353      if _re.search(r"<img<BACKSPACE>", t, _re.IGNORECASE):
     354          stripped = _re.sub(r"<[^>]+>", "", t).strip()
     355          if len(stripped) < 10:
```

## PLE2510 — core/quality.py:353
Invalid unescaped character backspace, use "\b" instead
```python
     348  
     349      # 1. Čisto-slikovni blok
     350      if _re.search(r"^\s*<(img|figure|svg)<BACKSPACE>", t, _re.IGNORECASE):
     351          return True
     352      # Blok koji sadrži SAMO sliku (img bez okolnog teksta)
>>   353      if _re.search(r"<img<BACKSPACE>", t, _re.IGNORECASE):
     354          stripped = _re.sub(r"<[^>]+>", "", t).strip()
     355          if len(stripped) < 10:
     356              return True
     357  
     358      # 2. TOC lista — niz linkova bez proze
```

## PLE2510 — core/quality.py:360
Invalid unescaped character backspace, use "\b" instead
```python
     355          if len(stripped) < 10:
     356              return True
     357  
     358      # 2. TOC lista — niz linkova bez proze
     359      if _re.search(
>>   360          r"(?is)<(ul|ol)<BACKSPACE>[^>]*>(?:\s*<li[^>]*>\s*<a<BACKSPACE>[^>]*>[^<]{1,120}</a>.*?</li>\s*){3,}</(?:ul|ol)>",
     361          t,
     362      ):
     363          return True
     364  
     365      # 3. Plain-text analiza
```

## PLE2510 — core/quality.py:360
Invalid unescaped character backspace, use "\b" instead
```python
     355          if len(stripped) < 10:
     356              return True
     357  
     358      # 2. TOC lista — niz linkova bez proze
     359      if _re.search(
>>   360          r"(?is)<(ul|ol)<BACKSPACE>[^>]*>(?:\s*<li[^>]*>\s*<a<BACKSPACE>[^>]*>[^<]{1,120}</a>.*?</li>\s*){3,}</(?:ul|ol)>",
     361          t,
     362      ):
     363          return True
     364  
     365      # 3. Plain-text analiza
```

## B023 — core/replacements.py:103
Function definition does not bind loop variable `rule`
```python
      98      """Primijeni pravila na plain tekst. Vraca (novi_tekst, fires)."""
      99      fires: list[Fire] = []
     100      for rule in rules:
     101  
     102          def repl(m):
>>   103              return rule.replace
     104  
     105          new_text, count = rule.pattern.subn(repl, text)
     106          if count > 0:
     107              fires.append(
     108                  Fire(
```

## F841 — epub/name_replacer.py:274
Local variable `sample` is assigned to but never used
```python
     269      groups_txt = ""
     270      for i, grp in enumerate(groups, 1):
     271          groups_txt += f"{i}. {' | '.join(grp)}\n"
     272  
     273      # Uzmemo sample teksta (prvih ~2000 znakova čistog teksta)
>>   274      sample = full_text_sample[:2000].strip()
     275  
     276      return """Ti si ekspert za književni prijevod na hrvatski jezik.
     277  
     278  Analziraš EPUB knjigu i trebaš normalizovati vlastita imena i nazive entiteta.
     279  
```

## B018 — epub/name_replacer.py:284
Found useless expression. Either assign it to a variable or remove it.
```python
     279  
     280  KONTEKST KNJIGE (uzorak teksta):
     281  """
     282  
     283  
>>   284  {sample}
     285  """
     286  
     287  KANDIDATI ZA NORMALIZACIJU (grupe srodnih oblika):
     288  {groups_txt}
     289  
```

## F821 — epub/name_replacer.py:284
Undefined name `sample`
```python
     279  
     280  KONTEKST KNJIGE (uzorak teksta):
     281  """
     282  
     283  
>>   284  {sample}
     285  """
     286  
     287  KANDIDATI ZA NORMALIZACIJU (grupe srodnih oblika):
     288  {groups_txt}
     289  
```

## F841 — epub/packager.py:195
Local variable `images_dir` is assigned to but never used
```python
     190          return
     191  
     192      # Nadji OPF i images dir
     193      opf = next(work_dir.rglob("*.opf"), None)
     194      base_dir = opf.parent if opf else work_dir
>>   195      images_dir = base_dir / "images"
     196  
     197      # 1. Ocisti atribute + stari spanovi + dropcap + ornament
     198      for ext in ("*.xhtml", "*.html", "*.htm"):
     199          for f in work_dir.rglob(ext):
     200              try:
```

## B023 — epub/styler.py:612
Function definition does not bind loop variable `dirname`
```python
     607  
     608          def _repl(m):
     609              b64 = m.group(2)
     610              h, ext = b64_hash_ext[b64]
     611              png_path = f"images/booklyfi-shared-{h}.{ext}"
>>   612              return _os_b7.path.relpath(png_path, dirname)
     613  
     614          new_text = RX.sub(_repl, text)
     615          if new_text != text:
     616              files[name] = new_text.encode("utf-8")
     617  
```

## F821 — network/http_client.py:101
Undefined name `MIN_INTERVAL_PER_PROVIDER`
```python
      96  
      97  
      98  def _humanize_wait(provider):
      99      """Čeka minimalni interval + jitter između 2 poziva prema istom provideru."""
     100      pu = (provider or "").upper()
>>   101      min_int = MIN_INTERVAL_PER_PROVIDER.get(pu, _DEFAULT_MIN_INTERVAL)
     102      with _humanize_lock:
     103          last = _last_call_ts.get(pu, 0.0)
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
```

## F821 — network/http_client.py:101
Undefined name `_DEFAULT_MIN_INTERVAL`
```python
      96  
      97  
      98  def _humanize_wait(provider):
      99      """Čeka minimalni interval + jitter između 2 poziva prema istom provideru."""
     100      pu = (provider or "").upper()
>>   101      min_int = MIN_INTERVAL_PER_PROVIDER.get(pu, _DEFAULT_MIN_INTERVAL)
     102      with _humanize_lock:
     103          last = _last_call_ts.get(pu, 0.0)
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
```

## F821 — network/http_client.py:102
Undefined name `_humanize_lock`
```python
      97  
      98  def _humanize_wait(provider):
      99      """Čeka minimalni interval + jitter između 2 poziva prema istom provideru."""
     100      pu = (provider or "").upper()
     101      min_int = MIN_INTERVAL_PER_PROVIDER.get(pu, _DEFAULT_MIN_INTERVAL)
>>   102      with _humanize_lock:
     103          last = _last_call_ts.get(pu, 0.0)
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
     107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
```

## F821 — network/http_client.py:103
Undefined name `_last_call_ts`
```python
      98  def _humanize_wait(provider):
      99      """Čeka minimalni interval + jitter između 2 poziva prema istom provideru."""
     100      pu = (provider or "").upper()
     101      min_int = MIN_INTERVAL_PER_PROVIDER.get(pu, _DEFAULT_MIN_INTERVAL)
     102      with _humanize_lock:
>>   103          last = _last_call_ts.get(pu, 0.0)
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
     107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
     108              _time_h.sleep(wait)
```

## F821 — network/http_client.py:104
Undefined name `_time_h`
```python
      99      """Čeka minimalni interval + jitter između 2 poziva prema istom provideru."""
     100      pu = (provider or "").upper()
     101      min_int = MIN_INTERVAL_PER_PROVIDER.get(pu, _DEFAULT_MIN_INTERVAL)
     102      with _humanize_lock:
     103          last = _last_call_ts.get(pu, 0.0)
>>   104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
     107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
     108              _time_h.sleep(wait)
     109          _last_call_ts[pu] = _time_h.time()
```

## F821 — network/http_client.py:107
Undefined name `_rand_h`
```python
     102      with _humanize_lock:
     103          last = _last_call_ts.get(pu, 0.0)
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
>>   107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
     108              _time_h.sleep(wait)
     109          _last_call_ts[pu] = _time_h.time()
     110  
     111  
     112  def _build_headers(provider, api_key=None, extra=None):
```

## F821 — network/http_client.py:108
Undefined name `_time_h`
```python
     103          last = _last_call_ts.get(pu, 0.0)
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
     107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
>>   108              _time_h.sleep(wait)
     109          _last_call_ts[pu] = _time_h.time()
     110  
     111  
     112  def _build_headers(provider, api_key=None, extra=None):
     113      """Standardni headeri s browser UA."""
```

## F821 — network/http_client.py:109
Undefined name `_last_call_ts`
```python
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
     107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
     108              _time_h.sleep(wait)
>>   109          _last_call_ts[pu] = _time_h.time()
     110  
     111  
     112  def _build_headers(provider, api_key=None, extra=None):
     113      """Standardni headeri s browser UA."""
     114      h = {
```

## F821 — network/http_client.py:109
Undefined name `_time_h`
```python
     104          now = _time_h.time()
     105          elapsed = now - last
     106          if elapsed < min_int:
     107              wait = (min_int - elapsed) + _rand_h.uniform(0.2, 1.5)
     108              _time_h.sleep(wait)
>>   109          _last_call_ts[pu] = _time_h.time()
     110  
     111  
     112  def _build_headers(provider, api_key=None, extra=None):
     113      """Standardni headeri s browser UA."""
     114      h = {
```

## F821 — network/provider_router.py:244
Undefined name `self`
```python
     239          return None
     240  
     241      svi_upper = {p.upper() for p in fleet.fleet.keys()}
     242      preferred = PROVIDER_PRIORITY.get(uloga, [])
     243      # FIX: filtriraj na providere koji imaju ključeve (izbjegni log spam)
>>   244      has_keys = {p.upper() for p, keys in self.fleet.fleet.items() if keys}
     245      ordered = [p for p in preferred if p in svi_upper and p.upper() in has_keys]
     246      for p in svi_upper:
     247          if p.upper() in has_keys and p not in ordered:
     248              ordered.append(p)
     249  
```

## F821 — processing/workers.py:442
Undefined name `self`
```python
     437                  max_tokens=500,
     438                  timeout=60,
     439              )
     440              _dt = time.time() - _t0
     441              if res:
>>   442                  self.log(
     443                      f"  ◀ QA {provider} ({model}) | {_dt:.1f}s | {len(res)}c", "tech"
     444                  )
     445              if not res:
     446                  continue
     447  
```

## F821 — stil_ai.py:1442
Undefined name `_UPOZORENO`
```python
    1437                  log_callback(_dmsg, "tech")
    1438              except Exception:
    1439                  pass
    1440  
    1441      # 6. Ornament za scenu
>>  1442      if not dodaj_ornament(soup, scena, res, fname) and scena not in _UPOZORENO:
    1443          _UPOZORENO.add(scena)
    1444          _omsg = f"      UPOZORENJE: nema ornamenta za scenu '{scena}'"
    1445          print(_omsg)
    1446          if log_callback:
    1447              try:
```

## F821 — stil_ai.py:1443
Undefined name `_UPOZORENO`
```python
    1438              except Exception:
    1439                  pass
    1440  
    1441      # 6. Ornament za scenu
    1442      if not dodaj_ornament(soup, scena, res, fname) and scena not in _UPOZORENO:
>>  1443          _UPOZORENO.add(scena)
    1444          _omsg = f"      UPOZORENJE: nema ornamenta za scenu '{scena}'"
    1445          print(_omsg)
    1446          if log_callback:
    1447              try:
    1448                  log_callback(_omsg, "warning")
```

## F821 — utils/logging.py:284
Undefined name `logger`
```python
     279              if kwargs:
     280                  msg += " | " + " ".join(
     281                      f"{k}={v}" for k, v in kwargs.items() if v is not None
     282                  )
     283              _logger_func = {
>>   284                  "info": logger.info,
     285                  "warning": logger.warning,
     286                  "error": logger.error,
     287                  "debug": logger.debug,
     288              }.get(nivo, logger.info)
     289              _logger_func(msg)
```

## F821 — utils/logging.py:285
Undefined name `logger`
```python
     280                  msg += " | " + " ".join(
     281                      f"{k}={v}" for k, v in kwargs.items() if v is not None
     282                  )
     283              _logger_func = {
     284                  "info": logger.info,
>>   285                  "warning": logger.warning,
     286                  "error": logger.error,
     287                  "debug": logger.debug,
     288              }.get(nivo, logger.info)
     289              _logger_func(msg)
     290          except Exception:
```

## F821 — utils/logging.py:286
Undefined name `logger`
```python
     281                      f"{k}={v}" for k, v in kwargs.items() if v is not None
     282                  )
     283              _logger_func = {
     284                  "info": logger.info,
     285                  "warning": logger.warning,
>>   286                  "error": logger.error,
     287                  "debug": logger.debug,
     288              }.get(nivo, logger.info)
     289              _logger_func(msg)
     290          except Exception:
     291              pass
```

## F821 — utils/logging.py:287
Undefined name `logger`
```python
     282                  )
     283              _logger_func = {
     284                  "info": logger.info,
     285                  "warning": logger.warning,
     286                  "error": logger.error,
>>   287                  "debug": logger.debug,
     288              }.get(nivo, logger.info)
     289              _logger_func(msg)
     290          except Exception:
     291              pass
     292      # 2026-10-24 C1: strukturirani zapis u SHARED_STATS["audit_events"]
```

## F821 — utils/logging.py:288
Undefined name `logger`
```python
     283              _logger_func = {
     284                  "info": logger.info,
     285                  "warning": logger.warning,
     286                  "error": logger.error,
     287                  "debug": logger.debug,
>>   288              }.get(nivo, logger.info)
     289              _logger_func(msg)
     290          except Exception:
     291              pass
     292      # 2026-10-24 C1: strukturirani zapis u SHARED_STATS["audit_events"]
     293      # (config.settings.SHARED_STATS — pravi objekat, ne utils.shared_state)
```

## VULTURE — core/kalkovi/kalkovi_da.py:47
unsatisfiable 'ternary' condition (100% confidence)
```python
      42          # modal + da + jednočlani prezent (najčešći slučaj)
      43          rezultat.append(
      44              (
      45                  rf"\b{oblik}\s+da\s+(\w+)",
      46                  lambda m, inf=infinitiv: (
>>    47                      f"{m.group(0).split('da')[0].rstrip()} {inf}" if False else r"\g<0>"
      48                  ),  # placeholder — koristimo dolje
      49              )
      50          )
      51      return rezultat
      52  
```
