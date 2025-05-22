-- MPV Lua Script: File Deletion for Infinite Loop Playlist
-- Place in ~/.config/mpv/scripts/delete_file.lua
-- Usage: Press 'd' twice to delete file, 'ESC' to cancel after first 'd'
-- Designed for: mpv --shuffle --loop=inf *

local delete_state = {
    pending = false,
    filepath = nil
}

-- Show initial delete confirmation prompt
local function show_delete_prompt()
    local filepath = mp.get_property("path")
    if not filepath then 
        mp.osd_message("No file currently loaded", 2)
        return 
    end
    
    delete_state.pending = true
    delete_state.filepath = filepath
    
    -- Extract filename for display
    local filename = filepath:match("([^/]+)$") or filepath
    mp.osd_message(string.format("Delete '%s'? Press d again to CONFIRM, ESC to CANCEL", filename), 5)
    
    -- Add ESC binding for cancellation
    mp.add_key_binding("esc", "cancel-delete", cancel_delete)
end

-- Clean up temporary state and key bindings
local function cleanup_delete_state()
    delete_state.pending = false
    delete_state.filepath = nil
    
    -- Remove temporary ESC binding
    mp.remove_key_binding("cancel-delete")
end

-- Cancel deletion operation
local function cancel_delete()
    mp.osd_message("Deletion cancelled", 2)
    cleanup_delete_state()
end

-- Execute file deletion
local function confirm_delete()
    if not delete_state.pending then return end
    
    local filepath = delete_state.filepath
    local playlist_pos = mp.get_property_number("playlist-pos", 0)
    local playlist_count = mp.get_property_number("playlist-count", 0)
    
    -- Since we're in infinite loop mode, always advance to next file first
    -- This releases the file handle while keeping MPV running
    mp.commandv("playlist-next", "force")
    
    -- Perform synchronous file deletion
    local delete_command = string.format("rm %q", filepath)
    local success = os.execute(delete_command) == 0
    
    -- Show result
    if success then
        local filename = filepath:match("([^/]+)$") or filepath
        mp.osd_message(string.format("Deleted: %s", filename), 3)
        
        -- Remove the deleted file from playlist to prevent future playback attempts
        -- Find and remove all instances of this file from playlist
        local current_playlist = mp.get_property_native("playlist")
        for i = #current_playlist, 1, -1 do
            if current_playlist[i].filename == filepath then
                mp.commandv("playlist-remove", i - 1) -- playlist is 0-indexed
            end
        end
    else
        mp.osd_message("Deletion failed - check permissions", 3)
    end
    
    cleanup_delete_state()
end

-- Handle d key press
local function handle_d_key()
    if delete_state.pending then
        -- Second press: confirm deletion
        confirm_delete()
    else
        -- First press: show prompt
        show_delete_prompt()
    end
end

-- Handle MPV shutdown to clean up state
local function on_shutdown()
    cleanup_delete_state()
end

-- Register main delete key binding
mp.add_key_binding("d", "delete-file", handle_d_key)

-- Register shutdown handler
mp.register_event("shutdown", on_shutdown)
