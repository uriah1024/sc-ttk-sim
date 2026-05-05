class ShipKinematics:
    def __init__(self, ship_name, flight_data):
        self.name = ship_name
        self.scm_speed = flight_data.get('scm_speed', 0.0)
        self.nav_speed = flight_data.get('nav_speed', 0.0)
        self.boost_speed = flight_data.get('boost_speed') or (self.scm_speed + 200.0)
        
        self.base_accel_ms2 = flight_data.get('base_accel_g', 0.0) * 9.81
        self.boost_accel_ms2 = self.base_accel_ms2 * flight_data.get('boost_accel_mult', 1.0)
        
        self.pre_delay = flight_data.get('pre_delay', 0.15)
        self.ramp_up = flight_data.get('ramp_up', 0.5)
        self.ramp_down = flight_data.get('ramp_down', 0.5)
        self.regen_delay = flight_data.get('regen_delay', 1.5)
        
        # --- BULLETPROOF VARIABLE CLAMPS ---
        self.cap_size = flight_data.get('cap_size', 20.0)
        if self.cap_size <= 0: self.cap_size = 20.0
            
        self.cap_regen_tick = flight_data.get('cap_regen_tick', 0.75)
        if self.cap_regen_tick <= 0: self.cap_regen_tick = 0.75
            
        self.cap_threshold_ratio = flight_data.get('cap_threshold_ratio', 0.25)
        if self.cap_threshold_ratio <= 0: self.cap_threshold_ratio = 0.25
            
        self.max_segments = flight_data.get('available_segments', 4)
        if self.max_segments <= 0: self.max_segments = 4
        
        self.idle_cost = flight_data.get('idle_cost', 1.0)
        if self.idle_cost <= 0: self.idle_cost = 1.0
            
        self.boost_tuning = flight_data.get('boost_tuning', 'blank')
        self.drag_multiplier = flight_data.get('drag_multiplier', 0.8)

    def generate_timeline(self, max_time, mode="SCM", dt=0.1, assigned_segments=4):
        timeline = []
        current_v = 0.0
        current_d = 0.0
        boost_cap = 100.0
        
        if self.base_accel_ms2 <= 0:
            return [{"time": round(t*dt, 1), "distance": 0, "velocity": 0, "boost": 100, "is_boosting": False} for t in range(int(max_time/dt)+1)]

        # Failsafe check to ensure assigned_segments is safely handled as an integer
        try:
            assigned_segments = int(assigned_segments)
        except (ValueError, TypeError):
            assigned_segments = self.max_segments

        safe_assigned = min(assigned_segments, self.max_segments)
        
        # --- 1. THE REGEN PENALTY (Applies to all ships) ---
        unallocated_segments = self.max_segments - safe_assigned
        penalty = unallocated_segments * (self.cap_size * self.cap_threshold_ratio)
        effective_cap_size = self.cap_size + penalty
        
        if self.cap_regen_tick > 0 and effective_cap_size > 0:
            time_to_regen_full = effective_cap_size / self.cap_regen_tick
            regen_pct_per_sec = 100.0 / time_to_regen_full
        else:
            regen_pct_per_sec = 10.0

        # --- 2. THE BOOST BURN BUFF (Interceptor & Capital Tuning) ---
        effective_idle_cost = self.idle_cost
        has_boost_buff = 'interceptor' in self.boost_tuning or 'capital' in self.boost_tuning
        
        if has_boost_buff :
            bonus_pips = safe_assigned - 1
            max_bonus_pips = max(1, self.max_segments - 1)
            
            drain_reduction = (bonus_pips / max_bonus_pips) * self.cap_threshold_ratio
            effective_idle_cost = self.idle_cost * (1.0 - drain_reduction)

        if effective_idle_cost > 0:
            self.boost_burn_time = self.cap_size / effective_idle_cost
        else:
            self.boost_burn_time = 20.0
  
        # THE FIX: Calculate drain percentage AFTER the burn time is updated!
        if self.boost_burn_time > 0:
            drain_pct_per_sec = 100.0 / self.boost_burn_time 
        else:
            drain_pct_per_sec = 20.0

        # --- STATE MACHINE TRACKER ---
        boost_state = "IDLE"
        state_timer = 0.0

        for tick in range(int(max_time / dt) + 1):
            t = tick * dt
            is_boosting_visually = False 

            if mode == "Boosted SCM":
                if boost_state == "IDLE" and boost_cap >= 100.0:
                    boost_state = "PRE_DELAY"
                    state_timer = self.pre_delay
                elif boost_state == "PRE_DELAY":
                    state_timer -= dt
                    if state_timer <= 0:
                        boost_state = "RAMP_UP"
                        state_timer = self.ramp_up
                elif boost_state == "RAMP_UP":
                    is_boosting_visually = True
                    boost_cap -= drain_pct_per_sec * dt
                    state_timer -= dt
                    if boost_cap <= 0:
                        boost_state = "RAMP_DOWN"
                        state_timer = self.ramp_down
                    elif state_timer <= 0:
                        boost_state = "BURNING"
                elif boost_state == "BURNING":
                    is_boosting_visually = True
                    boost_cap -= drain_pct_per_sec * dt
                    if boost_cap <= 0:
                        boost_cap = 0
                        boost_state = "RAMP_DOWN"
                        state_timer = self.ramp_down
                elif boost_state == "RAMP_DOWN":
                    state_timer -= dt
                    if state_timer <= 0:
                        boost_state = "REGEN_DELAY"
                        state_timer = self.regen_delay
                elif boost_state == "REGEN_DELAY":
                    state_timer -= dt
                    if state_timer <= 0:
                        boost_state = "RECHARGING"
                elif boost_state == "RECHARGING":
                    boost_cap += regen_pct_per_sec * dt
                    if boost_cap >= 100.0:
                        boost_cap = 100.0
                        boost_state = "IDLE"

            # --- ACCELERATION & DRAG MATH ---
            if boost_state == "BURNING":
                current_accel = self.boost_accel_ms2
                target_v = self.boost_speed
            elif boost_state == "RAMP_UP":
                progress = 1.0 - (max(0, state_timer) / self.ramp_up) if self.ramp_up > 0 else 1.0
                current_accel = self.base_accel_ms2 + ((self.boost_accel_ms2 - self.base_accel_ms2) * progress)
                target_v = self.boost_speed
            elif boost_state == "RAMP_DOWN":
                progress = (max(0, state_timer) / self.ramp_down) if self.ramp_down > 0 else 0.0
                current_accel = self.base_accel_ms2 + ((self.boost_accel_ms2 - self.base_accel_ms2) * progress)
                target_v = self.scm_speed
            else:
                current_accel = self.base_accel_ms2
                target_v = self.nav_speed if mode == "NAV" else self.scm_speed
                
            # --- FLIGHT PHYSICS ---
            if current_v < target_v:
                current_v += current_accel * dt
                if current_v > target_v: current_v = target_v
            elif current_v > target_v:
                drag_force = (current_v - target_v) * self.drag_multiplier * dt
                base_decel = self.base_accel_ms2 * dt
                current_v -= max(drag_force, base_decel)
                if current_v < target_v: current_v = target_v
                    
            current_d += current_v * dt
            
            timeline.append({
                "time": round(t, 2),
                "distance": round(current_d, 2),
                "velocity": round(current_v, 2),
                "boost": round(boost_cap, 1),
                "is_boosting": is_boosting_visually
            })
            
        return timeline