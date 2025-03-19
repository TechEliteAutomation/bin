#!/bin/bash
# Improved GitHub repository synchronization script
# Handles Git identity configuration before committing

# Configuration variables
BASE_DIR="/home/u/s"
LOG_FILE="/tmp/github-sync-$(date +%Y%m%d-%H%M%S).log"
ERROR_LOG="/tmp/github-sync-errors-$(date +%Y%m%d-%H%M%S).log"
# Git identity - modify these with your actual information
GIT_EMAIL="at253341@gmail.com"
GIT_NAME="TechEliteAutomation"

# Initialize counters
SYNC_SUCCESS=0
SYNC_FAILED=0

# Log function with timestamps
log() {
    echo "[INFO] $1" | tee -a "$LOG_FILE"
}

error_log() {
    echo "[ERROR] $1" | tee -a "$LOG_FILE" "$ERROR_LOG"
}

warning_log() {
    echo "[WARNING] $1" | tee -a "$LOG_FILE"
}

# Check if Git identity is configured
configure_git_identity() {
    local repo_path="$1"
    local config_scope="$2"  # Can be "--global" or "--local"
    
    # Check if email is configured
    if [ "$config_scope" = "--local" ]; then
        cd "$repo_path" || return 1
    fi
    
    if ! git config "$config_scope" user.email >/dev/null 2>&1; then
        log "Setting Git $config_scope email to $GIT_EMAIL"
        git config "$config_scope" user.email "$GIT_EMAIL"
    fi
    
    # Check if name is configured
    if ! git config "$config_scope" user.name >/dev/null 2>&1; then
        log "Setting Git $config_scope name to $GIT_NAME"
        git config "$config_scope" user.name "$GIT_NAME"
    fi
    
    return 0
}

# Sync a single repository
sync_repo() {
    local repo_dir="$1"
    local repo_name=$(basename "$repo_dir")
    
    # Change to repository directory
    cd "$repo_dir" || return 1
    
    # Get current branch
    local branch=$(git rev-parse --abbrev-ref HEAD)
    log "Syncing repository: $repo_name (branch: $branch)"
    
    # Configure Git identity for this repository
    configure_git_identity "$repo_dir" "--local"
    
    # Add all changes
    log "Adding all changes for $repo_name"
    git add . >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        error_log "Failed to add changes for $repo_name"
        return 1
    fi
    
    # Check if there are changes to commit
    if git diff-index --quiet HEAD --; then
        log "No changes to commit for $repo_name"
        return 0
    fi
    
    # Commit changes
    log "Committing changes for $repo_name"
    git commit -m "Auto-sync: $(date +%Y-%m-%d\ %H:%M:%S)" >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        error_log "Failed to commit changes for $repo_name"
        return 1
    fi
    
    # Push changes
    log "Pushing changes for $repo_name"
    git push origin "$branch" >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        error_log "Failed to push changes for $repo_name"
        return 1
    fi
    
    log "Successfully synced $repo_name"
    return 0
}

# Main execution
main() {
    log "Starting GitHub repository one-way synchronization (local to remote)"
    log "Base directory: $BASE_DIR"
    
    # Optional: Set global Git config
    # Uncomment the following line if you prefer global configuration
    # configure_git_identity "" "--global"
    
    # Find and process Git repositories
    log "Searching for Git repositories in $BASE_DIR"
    
    find "$BASE_DIR" -maxdepth 1 -type d | while read -r dir; do
        # Skip the base directory itself
        [ "$dir" = "$BASE_DIR" ] && continue
        
        # Check if it's a Git repository
        if [ -d "$dir/.git" ]; then
            if sync_repo "$dir"; then
                ((SYNC_SUCCESS++))
            else
                ((SYNC_FAILED++))
            fi
        else
            log "Skipping non-git directory: $dir"
        fi
    done
    
    # Summary
    log "Sync completed: $SYNC_SUCCESS successful, $SYNC_FAILED failed"
    
    if [ "$SYNC_FAILED" -gt 0 ]; then
        warning_log "Completed with errors. Check $ERROR_LOG for details."
        return 1
    else
        log "All repositories synced successfully."
        return 0
    fi
}

# Execute main function
main
exit $?
