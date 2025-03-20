#!/bin/bash

BASE_DIR="/home/u/s"
GIT_EMAIL="at253341@gmail.com"
GIT_NAME="TechEliteAutomation"
LOG_FILE="/var/log/git-sync.log"

# Log function
log() {
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"
log "Starting git sync process"

# Ensure GitHub's SSH key is trusted
ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null

for dir in "$BASE_DIR"/*; do
    [ -d "$dir/.git" ] || continue
    cd "$dir" || continue
    
    repo_name=$(basename "$dir")
    log "Processing repository: $repo_name"
    
    git config user.email "$GIT_EMAIL"
    git config user.name "$GIT_NAME"
    
    # Check for changes before committing
    if git status --porcelain | grep -q .; then
        log "Changes detected in $repo_name"
        
        # Stage all changes (respecting .gitignore)
        git add -A
        
        # Commit changes with timestamp
        git commit -m "Auto-sync: $(date "+%Y-%m-%d %H:%M:%S")"
        
        # Push changes
        if git push origin "$(git rev-parse --abbrev-ref HEAD)"; then
            log "Successfully pushed changes for $repo_name"
        else
            log "ERROR: Failed to push changes for $repo_name"
        fi
    else
        log "No changes detected in $repo_name"
    fi
done

log "Git sync process completed"
