#!/bin/bash

BASE_DIR="/home/u/s"
GIT_EMAIL="at253341@gmail.com"
GIT_NAME="TechEliteAutomation"

# Ensure GitHub's SSH key is trusted
ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null

for dir in "$BASE_DIR"/*; do
    [ -d "$dir/.git" ] || continue
    cd "$dir" || continue
    
    git config user.email "$GIT_EMAIL"
    git config user.name "$GIT_NAME"
    
    git add .
    git commit -m "Auto-sync: $(date "+%Y-%m-%d %H:%M:%S")" 2>/dev/null || true
    
    # Push only if there are changes
    if git diff --quiet; then
        echo "No changes to commit in $dir."
    else
        git push origin $(git rev-parse --abbrev-ref HEAD)
    fi
done
