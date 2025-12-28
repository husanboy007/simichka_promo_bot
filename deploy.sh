#!/bin/bash
echo "🚀 Kod serverga yuborilyapti..."
# Faylni serverga nusxalash
scp main.py root@194.242.57.51:/home/simichka_bot/
echo "✅ Fayl yuborildi. Bot qayta ishga tushyapti..."
# Serverda botni restart qilish
ssh root@194.242.57.51 "systemctl restart simichka_promo"
echo "🎉 Tayyor! Bot yangilandi."