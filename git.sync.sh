#!/bin/bash

BASE_DIR="/home/u/s"
GIT_EMAIL="at253341@gmail.com"
GIT_NAME="TechEliteAutomation"

for dir in "$BASE_DIR"/*; do
    [ -d "$dir/.git" ] || continue
    cd "$dir" || continue
    
    git config user.email "$GIT_EMAIL"
    git config user.name "$GIT_NAME"
    
    git add .
    git commit -m "Auto-sync: $(date +%Y-%m-%d %H:%M:%S)" 2>/dev/null || true
    git push origin $(git rev-parse --abbrev-ref HEAD)
done
