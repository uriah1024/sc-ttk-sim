const frames = SIM_DATA.frames;
const canvas = document.getElementById('simCanvas');
const ctx = canvas.getContext('2d');
const initialDistance = SIM_DATA.initialDistance;
const slider = document.getElementById('timeSlider');
const shieldFaces = SIM_DATA.shieldFaces;

// --- NEW: INITIALIZE CUSTOM IMAGES ---
const imgBg = new Image();
if (SIM_DATA.images.bg) imgBg.src = SIM_DATA.images.bg;

const imgTarget = new Image();
if (SIM_DATA.images.target) imgTarget.src = SIM_DATA.images.target;

const imgA1 = new Image();
if (SIM_DATA.images.a1) imgA1.src = SIM_DATA.images.a1;

const imgA2 = new Image();
if (SIM_DATA.images.a2) imgA2.src = SIM_DATA.images.a2;
// --- END NEW IMAGES ---

slider.max = frames.length > 0 ? frames.length - 1 : 0;

let currentFrame = 0;
let isPlaying = true;
let timer = null;
let flares = []; 

function draw() {
    if(currentFrame >= frames.length) {
        isPlaying = false;
        clearInterval(timer);
        currentFrame = frames.length - 1; 
    }
    
    const frame = frames[currentFrame];
    const cx = canvas.width / 2;
    const targetY = 80;
    
    const hasAttacker2 = frame.w2 && frame.w2.length > 0;
    const a1X = hasAttacker2 ? cx - 200 : cx;
    const a1Y = canvas.height - 40;
    const a2X = cx + 200;
    const a2Y = canvas.height - 40;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // --- DRAW BACKGROUND ---
    if (imgBg.src && imgBg.complete) {
        ctx.drawImage(imgBg, 0, 0, canvas.width, canvas.height);
    }
    
    // --- UI BARS: TOP LEFT TIMER ---
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(10, 10, 120, 30);
    ctx.fillStyle = '#aaaaaa';
    ctx.font = '14px Arial';
    ctx.fillText(`Time: ${frame.t.toFixed(2)}s`, 20, 30);
    
    // --- UI BARS: TARGET SHIP STATS ---
    const barWidth = 120;
    const barX = canvas.width - 250;
    
    // Calculate dynamic height for the background box based on shield type
    let targetHudHeight = (shieldFaces === 4) ? 235 : 160;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(barX - 10, 10, 260, targetHudHeight);

    let tY = 25; // Adjusted starting Y to pad inside the box

    // SHIELD BAR
    const globalAvgS = (frame.s[0] + frame.s[1] + frame.s[2] + frame.s[3]) / 4.0;
    
    if (shieldFaces === 4) {
        ctx.fillStyle = '#cccccc'; 
        ctx.fillText(`Shields (Quad): 🛡️ ${frame.tshp}`, barX, tY);
        tY += 5;
        
        const fNames = ['Front', 'Right', 'Rear', 'Left'];
        for(let i=0; i<4; i++) {
            tY += 18; 
            ctx.fillStyle = '#cccccc'; 
            ctx.font = '12px Arial';
            ctx.fillText(`${fNames[i]}:`, barX, tY);
            
            const quadBarWidth = 90; 
            const quadBarX = barX + 40; 
            
            // Health Bar
            ctx.fillStyle = '#333333'; ctx.fillRect(quadBarX, tY - 9, quadBarWidth, 8);
            ctx.fillStyle = '#00c8ff'; ctx.fillRect(quadBarX, tY - 9, quadBarWidth * frame.s[i], 8);
            
            if (frame.s[i] < 1.0 && frame.sr[i] < 1.0) {
                ctx.fillStyle = '#555555'; ctx.fillRect(quadBarX, tY + 1, quadBarWidth, 3);
                ctx.fillStyle = '#00ffcc'; ctx.fillRect(quadBarX, tY + 1, quadBarWidth * frame.sr[i], 3);
            }
            
            ctx.fillStyle = '#aaaaaa';
            ctx.fillText(`${(frame.s[i]*100).toFixed(0)}% 🛡️ ${frame.shp[i]}`, quadBarX + quadBarWidth + 10, tY); 
        }
        tY += 15;
        ctx.font = '14px Arial'; 
    } else {
        ctx.fillStyle = '#cccccc'; 
        ctx.fillText(`Shield: ${(globalAvgS * 100).toFixed(1)}% 🛡️ ${frame.tshp}`, barX, tY);
        ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
        ctx.fillStyle = '#00c8ff'; ctx.fillRect(barX, tY + 5, barWidth * globalAvgS, 8);
        
        if (globalAvgS < 1.0 && frame.sr[0] < 1.0) {
            ctx.fillStyle = '#555555'; ctx.fillRect(barX, tY + 14, barWidth, 3);
            ctx.fillStyle = '#00ffcc'; ctx.fillRect(barX, tY + 14, barWidth * frame.sr[0], 3);
        }
        tY += 20;
    }

    // ARMOR BAR WITH DYNAMIC COLORS & EMOJI
    tY += 30;
    ctx.fillStyle = '#cccccc'; 
    ctx.fillText(`Armor: ${(frame.a * 100).toFixed(1)}% `, barX, tY);
    
    let armorTextWidth = ctx.measureText(`Armor: ${(frame.a * 100).toFixed(1)}% `).width;
    ctx.fillStyle = '#ffaa00'; // Orange for physical
    ctx.fillText(`(${frame.atp}`, barX + armorTextWidth, tY);
    let physWidth = ctx.measureText(`(${frame.atp}`).width;
    
    ctx.fillStyle = '#cccccc';
    ctx.fillText(` / `, barX + armorTextWidth + physWidth, tY);
    let sepWidth = ctx.measureText(` / `).width;
    
    ctx.fillStyle = '#00ffff'; // Teal for energy
    ctx.fillText(`${frame.ate}) `, barX + armorTextWidth + physWidth + sepWidth, tY);
    let engWidth = ctx.measureText(`${frame.ate}) `).width;
    
    ctx.fillStyle = '#ffaa00'; // Match armor bar color
    ctx.fillText(`🧡 ${frame.ahp}`, barX + armorTextWidth + physWidth + sepWidth + engWidth, tY);

    ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
    ctx.fillStyle = '#ffaa00'; ctx.fillRect(barX, tY + 5, barWidth * frame.a, 8);

    // HULL HP BAR WITH EMOJI
    tY += 30;
    ctx.fillStyle = '#cccccc'; ctx.fillText(`Hull: ${(frame.h * 100).toFixed(1)}% 🤍 ${frame.hhp}`, barX, tY);
    ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
    ctx.fillStyle = '#aaaaaa'; ctx.fillRect(barX, tY + 5, barWidth * frame.h, 8);

    // POWER PLANT BAR WITH TEAL COLOR & EMOJI
    tY += 30;
    ctx.fillStyle = '#cccccc'; ctx.fillText(`P.Plant: ${(frame.pp * 100).toFixed(1)}% 🩵 ${frame.pphp}`, barX, tY);
    ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
    ctx.fillStyle = '#00ffff'; ctx.fillRect(barX, tY + 5, barWidth * frame.pp, 8);
    
    tY += 15;
    ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY, barWidth, 4);
    ctx.fillStyle = '#bb00ff'; ctx.fillRect(barX, tY, barWidth * frame.pdh, 4);
    
    if (frame.pdh < 1.0 && frame.pdr < 1.0) {
        ctx.fillStyle = '#441166'; ctx.fillRect(barX, tY + 5, barWidth, 2);
        ctx.fillStyle = '#eebbff'; ctx.fillRect(barX, tY + 5, barWidth * frame.pdr, 2);
    }

    // --- TARGET SHIP (FLIPPED 180 DEGREES) ---
    if (imgTarget.src && imgTarget.complete) {
        ctx.save();
        ctx.translate(cx, targetY);
        ctx.rotate(Math.PI); // Rotates 180 degrees
        ctx.drawImage(imgTarget, -40, -40, 80, 80);
        ctx.restore();
    } else {
        ctx.fillStyle = '#ff4444';
        ctx.beginPath();
        ctx.moveTo(cx, targetY - 25); 
        ctx.lineTo(cx + 10, targetY - 5); 
        ctx.lineTo(cx + 30, targetY + 15); 
        ctx.lineTo(cx + 10, targetY + 10);
        ctx.lineTo(cx, targetY + 5);       
        ctx.lineTo(cx - 10, targetY + 10);
        ctx.lineTo(cx - 30, targetY + 15); 
        ctx.lineTo(cx - 10, targetY - 5);
        ctx.fill();
    }
    
    // --- SHIELDS ---
    ctx.lineWidth = 6;
    if (shieldFaces === 4) {
        const gap = 0.1;
        ctx.strokeStyle = `rgba(0, 200, 255, ${Math.max(0.1, frame.s[2])})`;
        ctx.beginPath(); ctx.arc(cx, targetY, 45, 5*Math.PI/4 + gap, 7*Math.PI/4 - gap); ctx.stroke();
        
        ctx.strokeStyle = `rgba(0, 200, 255, ${Math.max(0.1, frame.s[1])})`;
        ctx.beginPath(); ctx.arc(cx, targetY, 45, 7*Math.PI/4 + gap, Math.PI/4 - gap + Math.PI*2); ctx.stroke();
        
        ctx.strokeStyle = `rgba(0, 200, 255, ${Math.max(0.1, frame.s[0])})`;
        ctx.beginPath(); ctx.arc(cx, targetY, 45, Math.PI/4 + gap, 3*Math.PI/4 - gap); ctx.stroke();
        
        ctx.strokeStyle = `rgba(0, 200, 255, ${Math.max(0.1, frame.s[3])})`;
        ctx.beginPath(); ctx.arc(cx, targetY, 45, 3*Math.PI/4 + gap, 5*Math.PI/4 - gap); ctx.stroke();
    } else {
        if (globalAvgS > 0) {
            ctx.strokeStyle = `rgba(0, 200, 255, ${Math.max(0.1, globalAvgS)})`;
            ctx.beginPath();
            ctx.arc(cx, targetY, 45, 0, Math.PI * 2);
            ctx.stroke();
        }
    }
    
    // --- ATTACKER 1 (LEAD) ---
    if (imgA1.src && imgA1.complete) {
        ctx.drawImage(imgA1, a1X - 40, a1Y - 40, 80, 80);
    } else {
        ctx.fillStyle = '#44ff44';
        ctx.beginPath();
        ctx.moveTo(a1X, a1Y - 25); ctx.lineTo(a1X + 10, a1Y - 5); ctx.lineTo(a1X + 30, a1Y + 15); 
        ctx.lineTo(a1X + 10, a1Y + 10); ctx.lineTo(a1X, a1Y + 5); ctx.lineTo(a1X - 10, a1Y + 10);
        ctx.lineTo(a1X - 30, a1Y + 15); ctx.lineTo(a1X - 10, a1Y - 5); ctx.fill();
    }

    // --- RESTORED: ATTACKER 2 (WINGMAN) SHIP ---
    if (hasAttacker2) {
        if (imgA2.src && imgA2.complete) {
            ctx.drawImage(imgA2, a2X - 40, a2Y - 40, 80, 80);
        } else {
            ctx.fillStyle = '#0088ff';
            ctx.beginPath();
            ctx.moveTo(a2X, a2Y - 25); ctx.lineTo(a2X + 10, a2Y - 5); ctx.lineTo(a2X + 30, a2Y + 15); 
            ctx.lineTo(a2X + 10, a2Y + 10); ctx.lineTo(a2X, a2Y + 5); ctx.lineTo(a2X - 10, a2Y + 10);
            ctx.lineTo(a2X - 30, a2Y + 15); ctx.lineTo(a2X - 10, a2Y - 5); ctx.fill();
        }
    }

    // --- FLARES ---
    if (isPlaying && frame.i && frame.i.length > 0) {
        frame.i.forEach(imp => {
            const x_off = imp[0];
            const p_type = imp[1];
            const owner = imp[2];
            
            let hitY = targetY + 15;
            if ((p_type === 1 || p_type === 2) && globalAvgS > 0) hitY = targetY + 45; 
            
            let hitX = cx + (x_off * 0.3);
            
            if (hasAttacker2) {
                if (owner === 1) hitX -= 15; 
                if (owner === 2) hitX += 35; 
            }
            
            flares.push({ x: hitX, y: hitY, type: p_type, life: 1.0 });
        });
    }

    for (let i = flares.length - 1; i >= 0; i--) {
        let f = flares[i];
        f.life -= 0.15; 
        if (f.life <= 0) { flares.splice(i, 1); continue; }
        ctx.beginPath();
        ctx.arc(f.x, f.y, (1 - f.life) * 15, 0, Math.PI * 2); 
        let alpha = Math.max(0, f.life);
        if (f.type === 2) ctx.fillStyle = `rgba(187, 0, 255, ${alpha})`; 
        else if (f.type === 1) ctx.fillStyle = `rgba(0, 255, 255, ${alpha})`; 
        else ctx.fillStyle = `rgba(255, 170, 0, ${alpha})`; 
        ctx.fill();
    }
    
    // --- V-FORMATION PROJECTILES ---
    frame.p.forEach(proj => {
        const x_off = proj[0];
        const dist_rem = proj[1];
        const p_type = proj[2]; 
        const owner = proj[3];
        
        let targetDestY = targetY + 15; 
        if ((p_type === 1 || p_type === 2) && globalAvgS > 0) targetDestY = targetY + 45; 
        
        let originX = (owner === 1) ? a1X : a2X;
        originX += x_off;
        let originY = (owner === 1) ? a1Y : a2Y;
        
        let targetDestX = cx + (x_off * 0.3);
        
        if (hasAttacker2) {
            if (owner === 1) targetDestX -= 15; 
            if (owner === 2) targetDestX += 35; 
        }
        
        const travelPct = 1.0 - (dist_rem / initialDistance);
        const currentX = originX + (targetDestX - originX) * travelPct;
        const currentY = originY + (targetDestY - originY) * travelPct;
        
        if (p_type === 2) ctx.fillStyle = '#bb00ff'; 
        else if (p_type === 1) ctx.fillStyle = '#00ffff'; 
        else ctx.fillStyle = '#ffaa00'; 
        
        const angle = Math.atan2(targetDestY - originY, targetDestX - originX);
        
        ctx.save();
        ctx.translate(currentX, currentY);
        ctx.rotate(angle);
        ctx.fillRect(-15, -2, 15, 4); 
        ctx.restore();
    });
    
    // --- WEAPON HUD (ATTACKER 1) ---
    let startX = 20;
    let startY = canvas.height - (frame.w1.length * 30) - 10;
    
    // A1 HUD Background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(startX - 10, startY - 30, 260, (frame.w1.length * 30) + 40);

    ctx.fillStyle = '#44ff44';
    ctx.font = 'bold 12px Arial';
    ctx.fillText(`🟢 A1 Weapons`, startX, startY - 15);
    
    frame.w1.forEach((wpn, idx) => {
        const isEnergy = wpn[0] === 1;
        ctx.fillStyle = '#cccccc'; ctx.font = '11px Arial'; ctx.fillText(`S${idx + 1}`, startX, startY);
        
        if (isEnergy) {
            const currentAmmo = wpn[1], maxAmmo = wpn[2], isRecharging = wpn[3];
            ctx.fillStyle = '#333333'; ctx.fillRect(startX + 25, startY - 8, 100, 8);
            ctx.fillStyle = isRecharging ? '#555555' : '#00ffff';
            ctx.fillRect(startX + 25, startY - 8, (currentAmmo / maxAmmo) * 100, 8);
            ctx.fillStyle = '#ffffff'; ctx.fillText(`${currentAmmo.toFixed(0)} / ${maxAmmo}`, startX + 135, startY);
        } else {
            const totalAmmo = wpn[1], heatPct = wpn[2], ammoFired = wpn[3], isOverheated = wpn[4];
            ctx.fillStyle = '#333333'; ctx.fillRect(startX + 25, startY - 8, 100, 8);
            ctx.fillStyle = isOverheated ? '#ff0000' : '#ffaa00';
            ctx.fillRect(startX + 25, startY - 8, Math.min(heatPct, 100) || 0, 8);
            ctx.fillStyle = isOverheated ? '#ff0000' : '#ffffff';
            const heatStatus = isOverheated ? '🔥🔥🔥' : `🔥: ${heatPct.toFixed(1)}%`;
            ctx.fillText(`${heatStatus} | Ammo: ${totalAmmo}`, startX + 135, startY);
        }
        startY += 30;
    });
    
    // --- WEAPON HUD (ATTACKER 2) ---
    if (hasAttacker2) {
        let startX2 = canvas.width - 320;
        let startY2 = canvas.height - (frame.w2.length * 30) - 10;
        
        // A2 HUD Background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(startX2 - 10, startY2 - 30, 260, (frame.w2.length * 30) + 40);

        ctx.fillStyle = '#0088ff';
        ctx.font = 'bold 12px Arial';
        ctx.fillText(`🔵 A2 Weapons`, startX2, startY2 - 15);
        
        frame.w2.forEach((wpn, idx) => {
            const isEnergy = wpn[0] === 1;
            ctx.fillStyle = '#cccccc'; ctx.font = '11px Arial'; ctx.fillText(`S${idx + 1}`, startX2, startY2);
            
            if (isEnergy) {
                const currentAmmo = wpn[1], maxAmmo = wpn[2], isRecharging = wpn[3];
                ctx.fillStyle = '#333333'; ctx.fillRect(startX2 + 25, startY2 - 8, 100, 8);
                ctx.fillStyle = isRecharging ? '#555555' : '#00ffff';
                ctx.fillRect(startX2 + 25, startY2 - 8, (currentAmmo / maxAmmo) * 100, 8);
                ctx.fillStyle = '#ffffff'; ctx.fillText(`${currentAmmo.toFixed(0)} / ${maxAmmo}`, startX2 + 135, startY2);
            } else {
                const totalAmmo = wpn[1], heatPct = wpn[2], ammoFired = wpn[3], isOverheated = wpn[4];
                ctx.fillStyle = '#333333'; ctx.fillRect(startX2 + 25, startY2 - 8, 100, 8);
                ctx.fillStyle = isOverheated ? '#ff0000' : '#ffaa00';
                ctx.fillRect(startX2 + 25, startY2 - 8, Math.min(heatPct, 100) || 0, 8);
                ctx.fillStyle = isOverheated ? '#ff0000' : '#ffffff';
                const heatStatus = isOverheated ? '🔥🔥🔥' : `🔥: ${heatPct.toFixed(1)}%`;
                ctx.fillText(`${heatStatus} | Ammo: ${totalAmmo}`, startX2 + 135, startY2);
            }
            startY2 += 30; 
        });
    }
    
    if (frame.d) {
        ctx.fillStyle = '#ff0000';
        ctx.font = 'bold 32px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(`TARGET DESTROYED`, cx, canvas.height / 2);
        ctx.textAlign = 'left'; 
    }
    
    if (isPlaying) {
        slider.value = currentFrame;
        currentFrame++;
    }
}

slider.addEventListener('input', (e) => {
    currentFrame = parseInt(e.target.value);
    isPlaying = false; 
    flares = []; 
    clearInterval(timer);
    draw(); 
});

document.getElementById('btnPlay').onclick = () => {
    if (currentFrame >= frames.length - 1) {
        currentFrame = 0; 
        flares = [];
    }
    isPlaying = !isPlaying;
    if(isPlaying) timer = setInterval(draw, 50); 
    else clearInterval(timer);
};

document.getElementById('btnRestart').onclick = () => {
    currentFrame = 0;
    slider.value = 0;
    isPlaying = true;
    flares = [];
    clearInterval(timer);
    timer = setInterval(draw, 50);
};

timer = setInterval(draw, 50);