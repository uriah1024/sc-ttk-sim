class ShipKinematics:
    def __init__(self, ship_name, flight_data):
        """
        Initializes the physics profile for a specific ship based on ingested DB data.
        """
        self.name = ship_name
        self.scm_speed = flight_data.get('scm_speed', 0.0)
        self.nav_speed = flight_data.get('nav_speed', 0.0)
        
        # Convert G-Force to meters per second squared (1G = 9.81 m/s^2)
        base_g = flight_data.get('base_accel_g', 0.0)
        self.base_accel_ms2 = base_g * 9.81
        
        boost_mult = flight_data.get('boost_accel_mult', 1.0)
        self.boost_accel_ms2 = self.base_accel_ms2 * boost_mult
        
        self.boost_burn_time = flight_data.get('boost_burn_time', 0.0)

    def calculate_state_at_time(self, t, mode="SCM"):
        """
        Calculates the exact distance traveled and current velocity at time 't'.
        Evaluates the flight in three distinct phases to ensure perfect physics curves.
        """
        if self.base_accel_ms2 <= 0:
            return {"time": t, "distance": 0.0, "velocity": 0.0}

        target_speed = self.nav_speed if mode == "NAV" else self.scm_speed
        
        # State tracking variables
        current_t = 0.0
        current_v = 0.0
        current_d = 0.0
        
        # PHASE 1: Boost Acceleration (Only applies if in Boosted SCM mode)
        if mode == "Boosted SCM" and self.boost_burn_time > 0:
            time_to_cap_with_boost = (target_speed - current_v) / self.boost_accel_ms2
            # The boost phase ends when either: 
            # 1. Boost fuel runs out, 2. The ship hits top speed, or 3. The requested time 't' is reached.
            boost_duration = min(self.boost_burn_time, time_to_cap_with_boost, t)
            
            if boost_duration > 0:
                # Standard kinematic formula: d = v*t + 0.5*a*t^2
                current_d += (current_v * boost_duration) + (0.5 * self.boost_accel_ms2 * (boost_duration ** 2))
                current_v += self.boost_accel_ms2 * boost_duration
                current_t += boost_duration
        
        # PHASE 2: Base Acceleration (Applies if time remains and we haven't hit the speed cap)
        if current_t < t and current_v < target_speed:
            time_to_cap = (target_speed - current_v) / self.base_accel_ms2
            time_remaining = t - current_t
            accel_duration = min(time_to_cap, time_remaining)
            
            if accel_duration > 0:
                current_d += (current_v * accel_duration) + (0.5 * self.base_accel_ms2 * (accel_duration ** 2))
                current_v += self.base_accel_ms2 * accel_duration
                current_t += accel_duration
                
        # PHASE 3: Coasting (Applies if the speed cap was reached but time still remains)
        if current_t < t:
            coast_duration = t - current_t
            # Acceleration is 0, so distance is just velocity * time
            current_d += current_v * coast_duration
            
        return {
            "time": t,
            "distance": round(current_d, 2),
            "velocity": round(current_v, 2)
        }