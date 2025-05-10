SAFE_CHARS='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!#$%&*+-/:;<=>?@_'
LC_ALL=C tr -dc "$SAFE_CHARS" < /dev/urandom | head -c 1000 > password.txt
