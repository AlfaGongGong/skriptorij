#!/data/data/com.termux/files/usr/bin/bash
# out.sh — kopira izlaz u clipboard; veliki ide na 0x0.st (URL u clipboard)
# Upotreba: out.sh <log_fajl>
LOG="$1"
[ ! -f "$LOG" ] && { echo "FAIL: nema $LOG"; exit 1; }
SIZE=$(wc -c < "$LOG")

if [ "$SIZE" -lt 50000 ]; then
    # Malo — ceo u clipboard
    if command -v termux-clipboard-set &>/dev/null; then
        cat "$LOG" | termux-clipboard-set
        echo ""
        echo "📋 Output ($SIZE B) u clipboard. Paste u chat."
    else
        echo "Log: $LOG"
    fi
else
    # Veliko — upload na 0x0.st, URL u clipboard
    if command -v curl &>/dev/null; then
        URL=$(curl -s --max-time 10 -F "file=@$LOG" https://0x0.st 2>/dev/null | tr -d '\n')
        if [ -n "$URL" ] && [[ "$URL" == https* ]]; then
            if command -v termux-clipboard-set &>/dev/null; then
                echo -n "$URL" | termux-clipboard-set
                echo ""
                echo "📤 Output veliki ($SIZE B). URL u clipboard:"
                echo "   $URL"
                echo "   (paste u chat — ja otvorim URL)"
            else
                echo "📤 Output veliki ($SIZE B). URL:"
                echo "   $URL"
            fi
        else
            # Fallback: zadnjih 100 linija
            if command -v termux-clipboard-set &>/dev/null; then
                tail -100 "$LOG" | termux-clipboard-set
                echo ""
                echo "📋 Upload pao. Zadnjih 100 linija u clipboard. Ceo: $LOG"
            fi
        fi
    else
        echo "Log: $LOG (nema curl za upload)"
    fi
fi
