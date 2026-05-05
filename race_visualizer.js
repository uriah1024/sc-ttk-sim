try {
    const shipData = window.SHIP_DATA;
    const maxDistance = window.MAX_DISTANCE;
    const maxTime = window.MAX_TIME;
    const shipImages = window.SHIP_IMAGES || {}; 

    if (!shipData) throw new Error("CRITICAL: Python failed to inject SHIP_DATA.");

    const slider = document.getElementById('timeSlider');
    const display = document.getElementById('timeDisplay');
    const trackContainer = document.getElementById('tracks');
    const playBtn = document.getElementById('playBtn');

    slider.max = maxTime;

    Object.keys(shipData).forEach(shipName => {
        const safeId = shipName.replace(/[^a-zA-Z0-9]/g, '');
        
        const lane = document.createElement('div');
        lane.className = 'lane';
        
        const hud = document.createElement('div');
        hud.className = 'hud-panel';
        
        const label = document.createElement('div');
        label.className = 'ship-label';
        label.innerText = shipName;
        
        const stats = document.createElement('div');
        stats.className = 'stats-label';
        stats.id = 'stats-' + safeId;
        stats.innerText = "0 m/s | 0 m"; 
        
        const boostWrap = document.createElement('div');
        boostWrap.className = 'boost-wrapper';
        boostWrap.innerHTML = `
            <span class="boost-icon" id="boost-icon-${safeId}">⚡</span>
            <div class="boost-container">
                <div class="boost-fill" id="boost-fill-${safeId}"></div>
            </div>
        `;
        
        hud.appendChild(label);
        hud.appendChild(stats);
        hud.appendChild(boostWrap);
        
        const track = document.createElement('div');
        track.className = 'track-panel';
        
        const grid = document.createElement('div');
        grid.className = 'lane-bg-lines';

        const startLine = document.createElement('div');
        startLine.className = 'start-line';
        
        const finishLine = document.createElement('div');
        finishLine.className = 'finish-line';
        
        const marker = document.createElement('div');
        marker.className = 'ship-marker';
        marker.id = 'marker-' + safeId;
        
        if (shipImages[shipName]) {
            marker.innerHTML = `<img src="${shipImages[shipName]}" class="ship-icon-img">`;
        } else {
            marker.innerHTML = `<div style="position: absolute; top: 0; left: 0; transform-origin: center center; transform: translate(-50%, -50%) rotate(90deg); font-size: 24px; filter: drop-shadow(0 0 5px rgba(79, 172, 254, 0.8));">🚀</div>`; 
        }
        
        track.appendChild(grid);
        track.appendChild(startLine);
        track.appendChild(finishLine);
        track.appendChild(marker);
        
        lane.appendChild(hud);
        lane.appendChild(track);
        trackContainer.appendChild(lane);
    });

    let internalTime = 0;

    function updateSimulation(timeOverride = null) {
        const t = timeOverride !== null ? timeOverride : parseFloat(slider.value);
        display.innerText = t.toFixed(1) + 's';
        
        const tickIndex = Math.floor(t * 10);

        Object.keys(shipData).forEach(shipName => {
            const timeline = shipData[shipName];
            const safeIndex = Math.min(tickIndex, timeline.length - 1);
            const state = timeline[safeIndex];
            
            const safeId = shipName.replace(/[^a-zA-Z0-9]/g, '');
            const marker = document.getElementById('marker-' + safeId);
            const stats = document.getElementById('stats-' + safeId);
            const bFill = document.getElementById('boost-fill-' + safeId);
            const bIcon = document.getElementById('boost-icon-' + safeId);
            
            const pct = 10 + (state.distance / maxDistance) * 85; 
            marker.style.left = pct + '%'; 
            
            stats.innerText = state.velocity.toFixed(0) + ' m/s | ' + state.distance.toFixed(0) + ' m';
            
            bFill.style.width = state.boost + '%';
            if (state.is_boosting) {
                bFill.style.background = '#00ffcc'; 
                bIcon.style.opacity = '1';
            } else {
                bFill.style.background = '#ff4444'; 
                bIcon.style.opacity = '0.3';
            }
        });
    }

    let isPlaying = false;
    let animationId;
    let lastTime = 0;

    function animate(timestamp) {
        // Initialize lastTime on the very first frame to perfectly sync the clocks
        if (!lastTime) lastTime = timestamp;
        
        let dt = (timestamp - lastTime) / 1000;
        lastTime = timestamp;

        // THE FIX: Prevent time from going backward if the browser lags
        if (dt < 0) dt = 0;

        internalTime += dt;

        if (internalTime >= maxTime) {
            internalTime = maxTime;
            slider.value = internalTime;
            updateSimulation(internalTime);
            pauseSimulation();
        } else {
            slider.value = internalTime; 
            updateSimulation(internalTime);
            animationId = requestAnimationFrame(animate);
        }
    }

    function pauseSimulation() {
        isPlaying = false;
        playBtn.innerText = "Play";
        cancelAnimationFrame(animationId);
        lastTime = 0; // Reset so the clock syncs fresh on the next play click
    }

    playBtn.addEventListener('click', () => {
        if (isPlaying) {
            pauseSimulation();
        } else {
            internalTime = parseFloat(slider.value);
            if (internalTime >= maxTime) {
                internalTime = 0;
                slider.value = 0;
            }
            isPlaying = true;
            playBtn.innerText = "Pause";
            lastTime = 0; // Clear the old clock so the animate loop creates a new one
            animationId = requestAnimationFrame(animate);
        }
    });

    slider.addEventListener('input', () => {
        if (isPlaying) pauseSimulation();
        internalTime = parseFloat(slider.value);
        updateSimulation();
    });

    // Run once to initialize the starting line
    updateSimulation();

} catch (err) {
    document.getElementById('debug').innerText = "System Error: " + err.message;
}