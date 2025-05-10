// ==UserScript==
// @name         yt.wl.js
// @namespace    http://tampermonkey.net/
// @version      1.2
// @description  Removes all videos from YouTube Watch Later playlist
// @author       TechEliteAutomation.com
// @match        *://www.youtube.com/playlist?list=WL*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';
    
    // Add a small control panel
    const addControlPanel = () => {
        const controlPanel = document.createElement('div');
        controlPanel.style.position = 'fixed';
        controlPanel.style.top = '70px';
        controlPanel.style.right = '20px';
        controlPanel.style.zIndex = '9999';
        controlPanel.style.padding = '10px';
        controlPanel.style.backgroundColor = 'rgba(33, 33, 33, 0.9)';
        controlPanel.style.borderRadius = '4px';
        controlPanel.style.color = 'white';
        
        const button = document.createElement('button');
        button.textContent = 'Start Clearing';
        button.style.padding = '8px 12px';
        button.style.cursor = 'pointer';
        button.onclick = startRemoval;
        
        const status = document.createElement('div');
        status.id = 'wl-clear-status';
        status.style.marginTop = '8px';
        status.textContent = 'Ready';
        
        controlPanel.appendChild(button);
        controlPanel.appendChild(status);
        document.body.appendChild(controlPanel);
    };
    
    // Set status message
    const setStatus = (message) => {
        const status = document.getElementById('wl-clear-status');
        if (status) status.textContent = message;
    };
    
    // Main removal function
    let removal_interval;
    const startRemoval = () => {
        setStatus('Starting removal process...');
        
        let count = 0;
        removal_interval = setInterval(() => {
            // Try multiple selector patterns since YouTube's DOM structure changes frequently
            const menuButtons = [
                ...document.querySelectorAll('ytd-playlist-video-renderer ytd-menu-renderer yt-icon-button'),
                ...document.querySelectorAll('ytd-playlist-video-renderer #button.dropdown-trigger'),
                ...document.querySelectorAll('ytd-playlist-video-renderer .ytd-menu-renderer button')
            ];
            
            // Find the first menu button from the top of the page
            const menuButton = menuButtons[0];
            
            if (menuButton) {
                // Click the menu button to open the dropdown
                menuButton.click();
                setStatus(`Opening menu for video ${++count}...`);
                
                // Wait for dropdown menu to appear
                setTimeout(() => {
                    // Try multiple selector patterns for remove button
                    const removeButtons = [
                        ...document.querySelectorAll('tp-yt-paper-listbox ytd-menu-service-item-renderer'),
                        ...document.querySelectorAll('ytd-menu-service-item-renderer'),
                        ...document.querySelectorAll('.ytd-menu-popup-renderer tp-yt-paper-item')
                    ];
                    
                    // Find the "Remove from Watch Later" option
                    const removeButton = Array.from(removeButtons).find(button => 
                        button.textContent.toLowerCase().includes('remove') || 
                        button.textContent.toLowerCase().includes('delete')
                    );
                    
                    if (removeButton) {
                        removeButton.click();
                        setStatus(`Removed video ${count}`);
                    } else {
                        // If we can't find the remove button, click elsewhere to close the menu
                        document.body.click();
                        setStatus('Could not find remove option, trying next video...');
                    }
                }, 500);
            } else {
                clearInterval(removal_interval);
                setStatus('Complete! All videos removed.');
                console.log('Watch Later playlist cleared');
            }
        }, 2000); // Longer delay to ensure UI responses
    };
    
    // Initialize after page loads
    window.addEventListener('load', () => {
        // Wait a bit for YouTube's JS to initialize
        setTimeout(addControlPanel, 2000);
    });
})();
