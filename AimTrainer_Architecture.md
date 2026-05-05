# Project Vision
A browser-based, 6DOF space combat aim trainer and telemetry analytics platform replicating Star Citizen's flight and weapon kinematics.
---

## The Tech Stack
- Host/Analyst: Python (Streamlit)
- Physics/Rendering Engine: Vanilla JavaScript + Three.js (Client-side HTML5 Canvas)
- Future Database: Supabase (JSON Telemetry payloads)
- Future Social: Discord Webhooks

## Immutable Architectural Rules
- Client-Side Execution: Python/Streamlit is strictly a "launcher" and dashboard. The 60FPS game loop MUST run entirely in the browser using JavaScript to prevent server latency.
- Delta Time ($\Delta t$): All physics calculations (movement, projectile speed, capacitor regen) must be multiplied by actual elapsed time to decouple the math from the user's monitor refresh rate (supports 60Hz to 240Hz+ natively).
- Stateless Flight Configs: Ship and weapon parameters (acceleration, weapon speed, capacitor size) must be loaded into browser memory on initialization. The game loop must never wait on a network/database request to calculate physics.
 - Hardware Native: The engine must utilize the browser's PointerLock API for infinite mouse tracking, and eventually the Gamepad API to natively read HOTAS/HOSAS/Pedal inputs (including vJoy devices).
 - Relative Velocity PIP: The Lead PIP is not a UI trick; it is a physical 3D coordinate calculated as: Target_Position + (Relative_Velocity * (Distance_to_Target / Weapon_Speed)).

---

## Current Epic: Epic 0.5 - The M&K 3D PoC
 - Player: Gladius (Base SCM: 235, Forward Accel: 14.5G, Lateral/Vert: 10.5G).
 - Weapons: 3x Panther Repeaters (Speed: 1800 m/s, RPM: 750, Alpha: 131).
 - Capacitor: 75 ammo pool. 0.25s regen delay. 15 ammo/sec regen rate.Target: 
 - Drone (3000 Shield HP, 4125 Armor HP, 10m hit radius).

1. The Flight Model (M&K)
- [ ] **6DOF M&K Controls**: Mouse controls Pitch/Yaw (via Pointer Lock API). W/S controls Forward/Retro thrust. A/D controls Lateral strafe. Space/Ctrl controls Vertical strafe.
- [ ] **Delta Time Physics**: The requestAnimationFrame loop uses actual time to ensure ship movement, projectile speed, and capacitor regen happen at the exact correct mathematical rates regardless of monitor refresh rate.
*Physics: Your ship will have a defined acceleration rate and a slight "drag" to simulate IFCS (Intelligent Flight Control System) slowing you down when you release the keys.*

2. The Target Drone
- [ ] We spawn a single enemy "drone" (a simple geometric shape) at 1,000 meters.
- [ ] It flies in a smooth but unpredictable pattern (e.g., a wide 3D figure-eight that occasionally changes speed).
- [ ] It does not shoot back. Its only job is to force you to maneuver.

3. The Lead PIP (The Star of the Show)
- [ ] The engine calculates the relative velocity between you and the drone.
- [ ] It projects a Lead PIP out in front of the drone based on a fixed weapon speed (e.g., 1400 m/s for laser repeaters).
**The Validation Test**: This is where you test the "Game Feel." If the drone is moving right, the PIP stretches right. If you press 'D' to strafe right and match its speed, the PIP must mathematically collapse back onto the drone's hull, exactly as it does in Star Citizen.

4. The Resource Loop
- [ ] **Capacitor Pool**: You start with a set pool of weapon energy (e.g., 100%).
- [ ] **Trigger Pull**: Holding the Left Mouse Button fires the weapons, draining the capacitor per shot based on the specific weapon's cost.
- [ ] **Regen Delay & Tick**: If you stop firing, the "Regen Delay" timer starts. Once it clears, the capacitor rapidly refills based on the "Regen Tick" rate. (This forces the player to learn trigger discipline instead of just spraying).

5. The Damage Model (The TTK Engine)
- [ ] **Projectiles & Hit Registration**: When fired, the engine checks if the Crosshair intersects the Lead PIP. If yes, it calculates the Distance to determine if the shot lands or disappears due to max range.
- [ ] **Shield Faces**: The target drone has 4 shield faces (Front, Back, Left, Right). The engine determines which face is hit based on your relative angle to the drone.
- [ ] **Hull & Armor**: Once a shield face drops (or if using Ballistics that penetrate), damage is applied to the hull armor.

6. The Win State (Time on Target)
- [ ] When your crosshair overlaps the PIP, the PIP turns green.
- [ ] We track "Time on Target" (ToT). The goal of the PoC is simply to see how long you can keep the PIP green during a 60-second round.
- [ ] The target is destroyed following our damage mechanics.

---

1. **Epic 1: The Core Kinematics Engine (The 2.5D Sandbox)**
 - [ ] Establishing the requestAnimationFrame loop with $\Delta t$ (Delta Time) scaling.
 - [ ] Defining the 2D canvas bounds, ship positioning, and translating the ships.csv acceleration limits into JavaScript variables.
 - [ ] Simulating environmental friction, momentum, and frame-rate drops.

2. **Epic 2: Input & Hardware Integration**
 - [ ] Connecting the HTML5 Gamepad API to read physical Virpil/VKB/CH hardware axes.
 - [ ] Implementing the Pointer Lock API for infinite mouse tracking (Pitch/Yaw).
 - [ ] Translating hardware axis data (-1.0 to 1.0) into the physics engine's X/Y/Z vectors.

3. **Epic 3: Combat Mechanics & The HUD**
 - [ ] Writing the geometry for the Target Box (scaling based on Z-Distance).
 - [ ] Calculating Relative Velocity to project the dynamic Lead PIP.
 - [ ] Implementing hit detection (when the crosshair overlaps the PIP and the trigger is pulled).

4. **Epic 4: AI & Scenario Management**
 - [ ] Creating a "Scenario Loader" (e.g., fighting a highly evasive Gladius vs. a slow, tanky Corsair).
 - [ ] Writing basic AI algorithms so the target ship changes its vectors (janking) to actively evade the player's PIP.

5. **Epic 5: Telemetry & The Supabase Brain**
 - [ ] Building the data packager that records the pilot's hit percentage, overshoot frequency, and time-to-neutralize.
 - [ ] Integrating the Supabase API to securely push this JSON data from the browser to your cloud database.
 - [ ] Implementing "Challenge Links" (Base64 URL encoding) for sharing specific scenario configurations.

6. **Epic 6: The Analytics & Social Ecosystem**
 - [ ] Writing the Python script to pull the Supabase data into your Streamlit dashboard for Org-wide analysis (e.g., HOTAS vs. HOSAS comparisons).
 - [ ] Configuring the Discord Webhooks to automatically announce new high scores and records in your server.


 ## Resources
 [MD Cheat sheet](https://www.markdownguide.org/cheat-sheet/)