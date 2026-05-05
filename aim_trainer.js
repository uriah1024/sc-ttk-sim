// --- 1. CONFIGURATION ---
const WEAPON_SPEED = 1800; 
const WEAPON_DMG = 131; 
const WEAPON_DELAY = 0.08; 
const MAX_CAP = 75;
const REGEN_DELAY = 0.25;
const REGEN_RATE = 15; 

const SCM_SPEED = 235;
const ACCEL_FWD = 14.5 * 9.81; 
const ACCEL_REV = 4.5 * 9.81;
const ACCEL_LAT = 10.5 * 9.81;

// ESP Tuning
const ESP_RADIUS_PX = 80; 
const ESP_SATURATION = 0.4; // Ship turns at 40% speed when dead center on target
const ESP_MAGNETISM = 0.20; // Pulls V-Joy input 20% toward PIP
const MAX_TURN_RATE = 1.8; 

let targetShield = 3000;
let targetArmor = 4125;
const targetRadius = 10; 

// --- 2. ENGINE SETUP ---
const canvas = document.getElementById('gameCanvas');
const crosshairDiv = document.getElementById('crosshair');
const uiPip = document.getElementById('ui-pip');
const espBubble = document.getElementById('esp-bubble');
const tetherLine = document.getElementById('tether-line');

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x000000, 0.0002);

const camera = new THREE.PerspectiveCamera(75, window.innerWidth / 750, 0.1, 10000);
camera.rotation.order = 'YXZ'; 
const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
renderer.setSize(window.innerWidth, 750);

// --- 3. ENVIRONMENT ---
const starGeo = new THREE.BufferGeometry();
const starMat = new THREE.PointsMaterial({color: 0xaaaaaa, size: 2});
const starVerts = [];
for(let i=0; i<2000; i++) {
    starVerts.push((Math.random()-0.5)*5000, (Math.random()-0.5)*5000, (Math.random()-0.5)*5000);
}
starGeo.setAttribute('position', new THREE.Float32BufferAttribute(starVerts, 3));
scene.add(new THREE.Points(starGeo, starMat));

const targetGeo = new THREE.BoxGeometry(targetRadius*2, targetRadius, targetRadius*2);
const targetMat = new THREE.MeshBasicMaterial({ color: 0xff0000, wireframe: true });
const targetMesh = new THREE.Mesh(targetGeo, targetMat);
scene.add(targetMesh);

// --- 4. STATE VARIABLES ---
let clock = new THREE.Clock();

let pitch = 0; let yaw = 0; let roll = 0;
let playerVel = new THREE.Vector3(0,0,0);

let targetPos = new THREE.Vector3(0, 0, -1000);
let lastTargetPos = new THREE.Vector3(0, 0, -1000);
let targetVel = new THREE.Vector3(0,0,0);

let projectiles = [];
let cap = MAX_CAP;
let lastFireTime = 0;
let isFiring = false;

// FPS Mouse State
let mouseX_px = window.innerWidth / 2;
let mouseY_px = 375;
let mouseX_ndc = 0; 
let mouseY_ndc = 0;

const keys = { w:false, s:false, a:false, d:false, ' ':false, c:false, q:false, e:false, Shift:false };
let isMouseOverCanvas = false;

// --- 5. SECURE INPUT HANDLING ---
canvas.addEventListener('mouseenter', () => { isMouseOverCanvas = true; });
canvas.addEventListener('mouseleave', () => { 
    isMouseOverCanvas = false; 
    isFiring = false; 
    for (let k in keys) keys[k] = false;
    // Reset Tether visual
    tetherLine.setAttribute('x2', '50%');
    tetherLine.setAttribute('y2', '50%');
});

canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    mouseX_px = e.clientX - rect.left;
    mouseY_px = e.clientY - rect.top;

    mouseX_ndc = (mouseX_px / rect.width) * 2 - 1;
    mouseY_ndc = -(mouseY_px / rect.height) * 2 + 1; 

    // Move Crosshair
    crosshairDiv.style.left = `${mouseX_px}px`;
    crosshairDiv.style.top = `${mouseY_px}px`;

    // Move Tether Line
    if (isMouseOverCanvas) {
        tetherLine.setAttribute('x2', mouseX_px);
        tetherLine.setAttribute('y2', mouseY_px);
    }
});

canvas.addEventListener('mousedown', (e) => { if(e.button === 0 && isMouseOverCanvas) isFiring = true; });
canvas.addEventListener('mouseup',   (e) => { if(e.button === 0) isFiring = false; });

document.addEventListener('keydown', (e) => { 
    if (isMouseOverCanvas && [' ', 'w', 'a', 's', 'd', 'c', 'q', 'e', 'shift'].includes(e.key.toLowerCase())) {
        e.preventDefault(); 
    }
    let k = e.key.toLowerCase();
    if (keys.hasOwnProperty(k)) keys[k] = true; 
}, { passive: false });

document.addEventListener('keyup', (e) => { 
    let k = e.key.toLowerCase();
    if (keys.hasOwnProperty(k)) keys[k] = false; 
});

// --- 6. PHYSICS LOOP ---
function animate() {
    requestAnimationFrame(animate);

    let dt = clock.getDelta();
    let now = clock.elapsedTime;
    let cx = canvas.width / 2;
    let cy = canvas.height / 2;

    // A. Target AI
    lastTargetPos.copy(targetPos);
    targetPos.x = Math.sin(now * 0.5) * 600;
    targetPos.y = Math.sin(now * 1.1) * 200;
    targetPos.z = -1000 + Math.cos(now * 0.5) * 400;
    targetMesh.position.copy(targetPos);
    targetVel.subVectors(targetPos, lastTargetPos).divideScalar(dt);

    // B. Lead PIP Projection to 2D UI
    let relVel = targetVel.clone().sub(playerVel);
    let distToTarget = camera.position.distanceTo(targetPos);
    let timeToImpact = distToTarget / WEAPON_SPEED;
    
    let pipPos = targetPos.clone().add(relVel.multiplyScalar(timeToImpact));
    let pipScreen = pipPos.clone().project(camera);
    let pipX_px = (pipScreen.x + 1) * cx;
    let pipY_px = (-pipScreen.y + 1) * cy;

    if (pipScreen.z < 1) {
        uiPip.style.left = `${pipX_px}px`;
        uiPip.style.top = `${pipY_px}px`;
        uiPip.style.display = 'block';
        
        espBubble.style.left = `${pipX_px}px`;
        espBubble.style.top = `${pipY_px}px`;
        espBubble.style.display = 'block';
    } else {
        uiPip.style.display = 'none';
        espBubble.style.display = 'none';
    }

    // C. ESP (Enhanced Stick Precision) Dampening & Magnetism
    let espMult = 1.0;
    let distToPip = Math.hypot(mouseX_px - pipX_px, mouseY_px - pipY_px);
    
    // Base V-Joy Deflection
    let defX = (mouseX_px - cx) / cx;
    let defY = (mouseY_px - cy) / cy;

    if (distToPip < ESP_RADIUS_PX && pipScreen.z < 1) {
        // 1. Dampening (Slower turning)
        let dampeningCurve = distToPip / ESP_RADIUS_PX; 
        espMult = ESP_SATURATION + ((1.0 - ESP_SATURATION) * dampeningCurve);
        
        // 2. Magnetism (Gently pull the turn vector toward the PIP)
        let pipDefX = (pipX_px - cx) / cx;
        let pipDefY = (pipY_px - cy) / cy;
        
        defX = defX * (1.0 - ESP_MAGNETISM) + (pipDefX * ESP_MAGNETISM);
        defY = defY * (1.0 - ESP_MAGNETISM) + (pipDefY * ESP_MAGNETISM);

        espBubble.style.borderColor = 'rgba(0, 255, 255, 0.6)'; // Highlight bubble

        // Perfect Alignment State
        if (distToPip < 15) {
            uiPip.style.backgroundColor = 'rgba(0, 255, 0, 0.4)'; // Fill PIP
        } else {
            uiPip.style.backgroundColor = 'transparent';
        }
    } else {
        espBubble.style.borderColor = 'rgba(0, 255, 255, 0.1)';
        uiPip.style.backgroundColor = 'transparent';
    }

    // D. Ship Turning Math
    let deadzone = 0.05; 
    if (Math.abs(defX) > deadzone) {
        let turnSpeed = (Math.abs(defX) - deadzone) * Math.sign(defX);
        yaw -= turnSpeed * MAX_TURN_RATE * espMult * dt; 
    }
    if (Math.abs(defY) > deadzone) {
        let turnSpeed = (Math.abs(defY) - deadzone) * Math.sign(defY);
        pitch -= turnSpeed * MAX_TURN_RATE * espMult * dt; 
        pitch = Math.max(-Math.PI/2, Math.min(Math.PI/2, pitch));
    }
    
    camera.rotation.set(pitch, yaw, roll, 'YXZ');
    if(keys.q) roll += 2 * dt;
    if(keys.e) roll -= 2 * dt;
    if(!keys.q && !keys.e) roll *= 0.95;

    // Translation Math
    let thrust = new THREE.Vector3(0,0,0);
    let boostMult = keys.Shift ? 2.0 : 1.0;

    if (keys.w) thrust.z -= ACCEL_FWD * boostMult;
    if (keys.s) thrust.z += ACCEL_REV * boostMult;
    if (keys.a) thrust.x -= ACCEL_LAT * boostMult;
    if (keys.d) thrust.x += ACCEL_LAT * boostMult;
    if (keys[' ']) thrust.y += ACCEL_LAT * boostMult;
    if (keys.c) thrust.y -= ACCEL_LAT * boostMult; 

    thrust.applyEuler(camera.rotation);
    playerVel.add(thrust.multiplyScalar(dt));

    if(thrust.lengthSq() === 0) playerVel.multiplyScalar(0.98); 
    if(playerVel.length() > SCM_SPEED * boostMult) playerVel.setLength(SCM_SPEED * boostMult);
    camera.position.add(playerVel.clone().multiplyScalar(dt));

    // E. True 1:1 Firing Mechanism
    let timeSinceFire = now - lastFireTime;
    if (isFiring && cap >= 1 && timeSinceFire >= WEAPON_DELAY) {
        cap -= 1;
        lastFireTime = now;
        
        let raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(new THREE.Vector2(mouseX_ndc, mouseY_ndc), camera);
        
        let projDir = raycaster.ray.direction.clone();
        projDir.x += (Math.random()-0.5)*0.003; 
        projDir.y += (Math.random()-0.5)*0.003;
        
        let projVel = projDir.multiplyScalar(WEAPON_SPEED).add(playerVel);
        let projMesh = new THREE.Mesh(new THREE.BoxGeometry(1,1,20), new THREE.MeshBasicMaterial({color: 0xffff00}));
        projMesh.position.copy(camera.position);
        projMesh.lookAt(camera.position.clone().add(projVel));
        
        projectiles.push({ mesh: projMesh, vel: projVel, life: 3.0 });
        scene.add(projMesh);
    }

    if (!isFiring && timeSinceFire > REGEN_DELAY) cap = Math.min(MAX_CAP, cap + (REGEN_RATE * dt));

    // Hit Detection
    for (let i = projectiles.length - 1; i >= 0; i--) {
        let p = projectiles[i];
        p.mesh.position.add(p.vel.clone().multiplyScalar(dt));
        p.life -= dt;
        
        if (p.mesh.position.distanceTo(targetPos) <= targetRadius) {
            scene.remove(p.mesh);
            projectiles.splice(i, 1);
            if (targetShield > 0) targetShield = Math.max(0, targetShield - WEAPON_DMG);
            else if (targetArmor > 0) targetArmor = Math.max(0, targetArmor - WEAPON_DMG);
            else { targetMesh.material.color.setHex(0x333333); uiPip.style.display = 'none'; espBubble.style.display = 'none'; }
        } else if (p.life <= 0) {
            scene.remove(p.mesh);
            projectiles.splice(i, 1);
        }
    }

    // Update UI
    document.getElementById('speed-txt').innerText = Math.round(playerVel.length());
    document.getElementById('dist-txt').innerText = Math.round(distToTarget);
    document.getElementById('cap-txt').innerText = Math.floor(cap);
    document.getElementById('cap-bar').style.width = (cap / MAX_CAP * 100) + '%';
    document.getElementById('shield-bar').style.width = (targetShield / 3000 * 100) + '%';
    document.getElementById('armor-bar').style.width = (targetArmor / 4125 * 100) + '%';

    renderer.render(scene, camera);
}
animate();