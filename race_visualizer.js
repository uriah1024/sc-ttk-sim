// Pull injected data from the window object
const shipData = window.SHIP_DATA;
const maxDistance = window.MAX_DISTANCE;
const maxTime = window.MAX_TIME;

const slider = document.getElementById('timeSlider');
const display = document.getElementById('timeDisplay');
const trackContainer = document.getElementById('tracks');

// Set slider max based on user input from Streamlit
slider.max = maxTime;

// 1. Initialize lanes for each ship
Object.keys(shipData).forEach(shipName => {
    const lane = document.createElement('div');
    lane.className = 'lane';
    
    const grid = document.createElement('div');
    grid.className = 'lane-bg-lines';
    lane.appendChild(grid);

    const label = document.createElement('div');
    label.className = 'ship-label';
    label.innerText = shipName;
    lane.appendChild(label);

    const marker = document.createElement('div');
    marker.className = 'ship-marker';
    // Create a safe HTML ID by removing spaces and special characters
    const safeId = shipName.replace(/[^a-zA-Z0-9]/g, '');
    marker.id = 'marker-' + safeId;
    
    const stats = document.createElement('div');
    stats.className = 'stats-label';
    stats.id = 'stats-' + safeId;
    marker.appendChild(stats);
    
    lane.appendChild(marker);
    trackContainer.appendChild(lane);
});

// 2. Update function to redraw ships when slider moves
function updateSimulation() {
    const t = parseFloat(slider.value);
    display.innerText = t.toFixed(1) + 's';
    
    // Map time to the pre-calculated array index (10 ticks per second)
    const tickIndex = Math.floor(t * 10);

    Object.keys(shipData).forEach(shipName => {
        const timeline = shipData[shipName];
        const safeIndex = Math.min(tickIndex, timeline.length - 1);
        const state = timeline[safeIndex];
        
        const safeId = shipName.replace(/[^a-zA-Z0-9]/g, '');
        const marker = document.getElementById('marker-' + safeId);
        const stats = document.getElementById('stats-' + safeId);
        
        // Calculate visual width (min 2% so it's always visible on the start line)
        const pct = Math.max(2, (state.distance / maxDistance) * 100);
        marker.style.width = pct + '%';
        marker.style.left = '0'; 
        
        stats.innerText = state.velocity.toFixed(0) + ' m/s | ' + state.distance.toFixed(0) + ' m';
    });
}

// Bind the slider to the update function
slider.addEventListener('input', updateSimulation);

// Run once on load to initialize the start line
updateSimulation();