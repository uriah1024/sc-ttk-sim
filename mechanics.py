import random
from data_manager import DataTransformer, get_ship_shield_size

class Weapon:
    def __init__(self, data, ship_ammo_mod=1.0, ship_regen_mod=1.0):
        ammo_mod = ship_ammo_mod if ship_ammo_mod > 0 else 1.0
        regen_mod = ship_regen_mod if ship_regen_mod > 0 else 1.0
        
        self.name = data.get('Weapon_Name', 'Unknown')
        self.size = DataTransformer.get_num(data.get('Weapon_Size'), is_int=True)
        w_type = str(data.get('Weapon_Type', '')).lower()
        self.owner = 1 
        
        if 'distortion' in w_type:
            self.damage_type = 'distortion'
        else:
            self.damage_type = 'ballistic' if 'ballistic' in w_type else 'energy'
        
        self.alpha_damage = DataTransformer.get_num(data.get('Alpha_Dmg'))
        self.rpm = DataTransformer.get_num(data.get('Wpn_RPM'))
        if self.rpm <= 0: self.rpm = 60.0 
        
        self.speed = DataTransformer.get_num(data.get('Ammo_Speed'))
        self.max_pen = DataTransformer.get_num(data.get('Pen_Distance'))
        
        self.time_between_shots = 60.0 / self.rpm
        self.time_since_last_shot = 0.0
        self.time_since_last_fired = 0.0

        raw_ammo_qty = DataTransformer.get_num(data.get('Ammo_Quantity'))

        self.is_energy = self.damage_type in ['energy', 'distortion']
        if self.is_energy:
            base_cap = DataTransformer.get_num(data.get('Capacitor_Max_Ammo'))
            base_regen = DataTransformer.get_num(data.get('Capacitor_Max_Regen_Sec'))
            self.regen_delay = DataTransformer.get_num(data.get('Capacitor_Cooldown'))
            
            if base_cap <= 0:
                if raw_ammo_qty > 0 and raw_ammo_qty != 999999.0:
                    base_cap = raw_ammo_qty
                elif 'cannon' in w_type:
                    base_cap, base_regen = 25.0, 3.0
                elif 'repeater' in w_type:
                    base_cap, base_regen = 75.0, 15.0
                else:
                    base_cap, base_regen = 50.0, 10.0
                    
            if self.regen_delay <= 0: self.regen_delay = 1.0 
            
            self.cap_max = base_cap * ammo_mod
            self.regen_per_sec = base_regen * regen_mod
                
            self.current_ammo = self.cap_max
            self.is_recharging = False
            self.time_since_trigger_released = 0.0 
        else:
            base_total_ammo = raw_ammo_qty if raw_ammo_qty > 0 else 10000 
            self.total_ammo = base_total_ammo * ammo_mod
            self.initial_ammo = self.total_ammo
            
            self.heat_per_shot = DataTransformer.get_num(data.get('Heat_Per_Shot'))
            self.cooling_delay = DataTransformer.get_num(data.get('Cooling_Delay')) 
            self.cooling_per_sec = DataTransformer.get_num(data.get('Colling_Seconds')) 
            
            self.max_heat = DataTransformer.get_num(data.get('Overheat_Max_Round')) * self.heat_per_shot
            if self.max_heat <= 0.0 or self.heat_per_shot <= 0.0:
                self.max_heat = 999999.0 
                
            self.overheat_cooldown = DataTransformer.get_num(data.get('Overheat_Max_Cooldown')) 
            self.current_heat = 0.0
            self.overheat_timer = 0.0
            self.is_overheated = False

    def update(self, dt, trigger_pulled, override_recharge=False):
        self.time_since_last_shot += dt
        self.time_since_last_fired += dt
        fired = False

        if self.is_energy:
            if self.is_recharging:
                local_trigger = False
                if self.current_ammo >= self.cap_max:
                    self.is_recharging = False 
                    local_trigger = trigger_pulled
                # FIX: Only break out of recharge if we actually have at least 1 shot ready!
                elif override_recharge and trigger_pulled and self.current_ammo >= 1.0:
                    local_trigger = True
                    self.is_recharging = False 
            else:
                local_trigger = trigger_pulled
                if self.current_ammo < 1.0 and local_trigger:
                    self.is_recharging = True 
                    local_trigger = False

            if not local_trigger:
                self.time_since_last_shot = min(self.time_since_last_shot, self.time_between_shots)

            if local_trigger:
                self.time_since_trigger_released = 0.0 
                if self.time_since_last_shot >= self.time_between_shots and self.current_ammo >= 1.0:
                    self.current_ammo -= 1.0
                    self.time_since_last_shot -= self.time_between_shots 
                    fired = True
                    if self.current_ammo < 1.0:
                        self.is_recharging = True
            else:
                self.time_since_trigger_released += dt
                if self.time_since_trigger_released >= self.regen_delay:
                    self.current_ammo = min(self.cap_max, self.current_ammo + (self.regen_per_sec * dt))
        else:
            local_trigger = trigger_pulled
            
            if self.is_overheated:
                local_trigger = False 
                self.overheat_timer -= dt
                if self.overheat_timer <= 0:
                    self.is_overheated = False
                    self.current_heat = 0.0

            if not local_trigger:
                self.time_since_last_shot = min(self.time_since_last_shot, self.time_between_shots)

            if local_trigger and self.total_ammo > 0:
                if self.time_since_last_shot >= self.time_between_shots:
                    self.total_ammo -= 1
                    self.current_heat += self.heat_per_shot
                    self.time_since_last_shot -= self.time_between_shots 
                    self.time_since_last_fired = 0.0
                    fired = True
                    if self.current_heat >= self.max_heat:
                        self.is_overheated = True
                        self.overheat_timer = self.overheat_cooldown
            
            if not fired and not self.is_overheated and self.time_since_last_fired >= self.cooling_delay:
                self.current_heat = max(0.0, self.current_heat - (self.cooling_per_sec * dt))

        return fired

class Projectile:
    def __init__(self, weapon, initial_distance, x_offset=0.0):
        self.weapon = weapon
        self.distance_remaining = initial_distance
        self.speed = weapon.speed
        self.x_offset = x_offset
        self.is_energy = weapon.damage_type == 'energy'
        self.is_distortion = weapon.damage_type == 'distortion'
        self.owner = getattr(weapon, 'owner', 1)
        
    def update(self, dt):
        self.distance_remaining -= self.speed * dt
        return self.distance_remaining <= 0

class DefenderLoadout:
    def __init__(self, ship_name, database, target_pp_name=None):
        self.name = ship_name
        ship_data = database.ships.get(ship_name, {})
        config_data = database.ship_configs.get(ship_name, {})
        
        self.armor_hp = DataTransformer.get_num(ship_data.get('Armor_HP'))
        self.max_armor_hp = self.armor_hp 
        
        self.deflection = {
            'ballistic': DataTransformer.get_num(ship_data.get('Armor_Deflection_Threshold_Physical')), 
            'energy': DataTransformer.get_num(ship_data.get('Armor_Deflection_Threshold_Energy')),
            'distortion': DataTransformer.get_num(ship_data.get('Armor_Deflection_Threshold_Distortion', 0.0))
        }
        
        armor_dist_mod = DataTransformer.get_multiplier(ship_data.get('Armor_Dmg_Mod_Dist'))
        self.hull_mod = {
            'ballistic': DataTransformer.get_multiplier(ship_data.get('Armor_Damage_Mod_Phys')), 
            'energy': DataTransformer.get_multiplier(ship_data.get('Armor_Dmg_Mod_Engy')),
            'distortion': armor_dist_mod if armor_dist_mod > 0 else 1.0
        }

        self.hull_parts = {}
        body_hp = config_data.get('body_hp', 0)
        nose_hp = config_data.get('nose_hp', 0)
        tail_hp = config_data.get('tail_hp', 0)
        
        # Rule: If no vital HP exists, set hull HP to 1.
        if body_hp <= 0 and nose_hp <= 0 and tail_hp <= 0:
            self.hull_parts['body'] = {'hp': 1.0, 'max_hp': 1.0, 'parent': None, 'transfer_rate': 0.0, 'is_vital': True}
        else:
            if body_hp > 0: self.hull_parts['body'] = {'hp': body_hp, 'max_hp': body_hp, 'parent': None, 'transfer_rate': 0.0, 'is_vital': True}
            if nose_hp > 0: self.hull_parts['nose'] = {'hp': nose_hp, 'max_hp': nose_hp, 'parent': None, 'transfer_rate': 0.0, 'is_vital': True}
            if tail_hp > 0: self.hull_parts['tail'] = {'hp': tail_hp, 'max_hp': tail_hp, 'parent': None, 'transfer_rate': 0.0, 'is_vital': True}

        # --- SANITIZE HULL PARTS ---
        # Remove any parts that are blank, None, or 0 from the database
        clean_hull = {}
        for part_name, stats in self.hull_parts.items():
            hp_val = stats.get('hp')
            # Check if it's not None, not an empty string, and greater than 0
            if hp_val is not None and str(hp_val).strip() != "" and float(hp_val) > 0:
                clean_hull[part_name] = stats
        
        self.hull_parts = clean_hull

        # Extreme safety fallback: If the database is completely empty for a ship,
        # give it a 1 HP dummy body so the math engine doesn't divide-by-zero or crash.
        if not self.hull_parts:
            self.hull_parts = {'body': {'hp': 1, 'max_hp': 1}}

        self.shield_slots = config_data.get('shield_count', 1)
        self.shield_faces = 1.0 
        
        self.shield_hp = {'Front': 0.0, 'Right': 0.0, 'Rear': 0.0, 'Left': 0.0}
        self.max_shield_hp_per_face = 0.0
        self.max_shield_hp = 0.0 
        self.max_total_shield_hp = 0.0
        
        self.shield_resist = {'ballistic': 0.0, 'energy': 0.0} 
        self.shield_absorp_max = {'ballistic': 0.45, 'energy': 1.0, 'distortion': 1.0}
        self.shield_absorp_min = {'ballistic': 0.0, 'energy': 1.0, 'distortion': 1.0}
        
        self.shield_gen_dist_hp = 0.0
        self.shield_res_dist_max = 0.0
        self.shield_res_dist_min = 0.0
        
        self.time_since_last_hit = {'Front': 0.0, 'Right': 0.0, 'Rear': 0.0, 'Left': 0.0}
        self.shield_regen_delay = 0.0
        self.shield_down_delay = 0.0 
        self.shield_dmg_delay = 0.0
        self.total_regen_rate = 0.0
        
        ship_pp_config = database.ship_pp_configs.get(ship_name, {})
        pp_name = target_pp_name if target_pp_name else ship_pp_config.get('Default_PP_Component', 'JS-300')
        pp_data = database.power_plants.get(pp_name, {})
        
        pp_length = DataTransformer.get_num(pp_data.get('PP_Length_(m)'))
        if pp_length <= 0: pp_length = 2.21
        
        pp_width = DataTransformer.get_num(pp_data.get('PP_Width_(m)'))
        if pp_width <= 0: pp_width = 1.5
        
        self.ship_length = DataTransformer.get_num(ship_data.get('Length'))
        if self.ship_length <= 0: self.ship_length = 20.0 
        
        self.ship_width = DataTransformer.get_num(ship_data.get('Width'))
        if self.ship_width <= 0: self.ship_width = 15.0
        
        custom_dist = DataTransformer.get_num(ship_pp_config.get('Location_Distance_From_Nose'))
        
        if custom_dist > 0:
            self.pp_depth = custom_dist - (pp_length / 2.0)
            depth_front = custom_dist - (pp_length / 2.0)
            depth_rear = (self.ship_length - custom_dist) - (pp_length / 2.0)
        else:
            self.pp_depth = (self.ship_length / 2.0) - (pp_length / 2.0)
            depth_front = self.pp_depth
            depth_rear = depth_front
            
        if self.pp_depth < 0: self.pp_depth = 0.0
        
        depth_side = (self.ship_width / 2.0) - (pp_width / 2.0)
        
        self.pp_depth_map = {
            'Front': max(0.0, depth_front),
            'Rear': max(0.0, depth_rear),
            'Left': max(0.0, depth_side),
            'Right': max(0.0, depth_side)
        }
            
        self.comp_hull_mod = 0.4 
        self.pp_hp = DataTransformer.get_num(pp_data.get('PP_HP', 350.0))
        self.max_pp_hp = self.pp_hp
        
        self.pp_dist_hp = DataTransformer.get_num(pp_data.get('PP_Dist_Shutdown_Dmg', 10000.0))
        self.max_pp_dist_hp = self.pp_dist_hp
        
        self.pp_dist_decay_delay = DataTransformer.get_num(pp_data.get('PP_Dist_Decay_Delay', pp_data.get('Dist_Decay_Delay', 5.0)))
        if self.pp_dist_decay_delay <= 0: self.pp_dist_decay_delay = 5.0
        
        self.pp_dist_decay_rate = DataTransformer.get_num(pp_data.get('PP_Dist_Decay_Rate', pp_data.get('Dist_Decay_Rate', 100.0)))
        if self.pp_dist_decay_rate <= 0: self.pp_dist_decay_rate = 100.0
        
        self.time_since_last_dist_hit = 0.0
        
        phys_mod = DataTransformer.get_num(pp_data.get('PP_Dmg_Mod_Phys'))
        engy_mod = DataTransformer.get_num(pp_data.get('PP_Dmg_Mod_Engy'))
        dist_mod = DataTransformer.get_num(pp_data.get('PP_Dmg_Mod_Dist'))
        
        self.pp_mod = {
            'ballistic': phys_mod if phys_mod > 0 else 0.85,
            'energy': engy_mod if engy_mod > 0 else 0.70,
            'distortion': dist_mod if dist_mod > 0 else 1.0
        }
        
        self.is_destroyed = False
        self.death_reason = "" 

    def equip_shields(self, shield_name, database):
        s_data = database.shields.get(shield_name)
        if not s_data: return
        
        hp_per_shield = DataTransformer.get_num(s_data.get('Shield_HP'))
        shield_size = DataTransformer.get_num(s_data.get('Shield_Size'), is_int=True)
        
        self.shield_faces = 4.0 if shield_size >= 3 else 1.0
        
        self.max_shield_hp_per_face = (hp_per_shield * self.shield_slots) / self.shield_faces
        for face in self.shield_hp:
            self.shield_hp[face] = self.max_shield_hp_per_face
            
        self.max_shield_hp = hp_per_shield * self.shield_slots 
        self.max_total_shield_hp = self.max_shield_hp
        
        regen_delay = DataTransformer.get_num(s_data.get('Regen_Delay'))
        shield_regen_delay = DataTransformer.get_num(s_data.get('Shield_Regen_Delay'))
        
        down_delay = DataTransformer.get_num(s_data.get('Shield_Down_Delay'))
        dmg_delay = DataTransformer.get_num(s_data.get('Shield_Dmg_Delay'))
        
        if down_delay <= 0: down_delay = regen_delay if regen_delay > 0 else (shield_regen_delay if shield_regen_delay > 0 else 5.0)
        if dmg_delay <= 0: dmg_delay = regen_delay if regen_delay > 0 else (shield_regen_delay if shield_regen_delay > 0 else 5.0)
        
        self.shield_down_delay = down_delay
        self.shield_dmg_delay = dmg_delay
        self.shield_regen_delay = down_delay 
        
        rate = DataTransformer.get_num(s_data.get('Regen_Rate'))
        if rate <= 0: rate = DataTransformer.get_num(s_data.get('Shield_Regen_Rate'))
        if rate <= 0: rate = 150.0 
        self.total_regen_rate = rate * self.shield_slots
        
        shd_dist_hp = DataTransformer.get_num(s_data.get('SHD_Dist_Shutdown_Dmg'))
        self.shield_gen_dist_hp = (shd_dist_hp * self.shield_slots) if shd_dist_hp > 0 else 5000.0
        
        res_phys = DataTransformer.get_num(s_data.get('SHD_Res_Phys_Max'))
        res_ener = DataTransformer.get_num(s_data.get('SHD_Res_Engy_Max'))
        
        self.shield_resist['ballistic'] = res_phys / 100.0 if res_phys > 0 else 0.0
        self.shield_resist['energy'] = res_ener / 100.0 if res_ener < 0 else 0.0
        
        def get_pct(raw_val, default):
            if raw_val is None or raw_val == '': return default
            v = DataTransformer.get_num(raw_val)
            return v / 100.0 if v > 1.0 else v
            
        self.shield_res_dist_max = get_pct(s_data.get('SHD_Res_Dist_Max'), 0.95)
        self.shield_res_dist_min = get_pct(s_data.get('SHD_Res_Dist_Min'), 0.75)
            
        self.shield_absorp_max = {
            'ballistic': get_pct(s_data.get('Shd_Absorb_Phys_Max'), 0.45),
            'energy': get_pct(s_data.get('SHD_Absorb_Engy_Max'), 1.0),
            'distortion': get_pct(s_data.get('SHD_Absorb_Dist_Max'), 1.0)
        }
        self.shield_absorp_min = {
            'ballistic': get_pct(s_data.get('Shd_Absorb_Phys_Min'), 0.0),
            'energy': get_pct(s_data.get('SHD_Absorb_Engy_Min'), 1.0),
            'distortion': get_pct(s_data.get('SHD_Absorb_Dist_Min'), 1.0)
        }

    def get_current_shield_hp(self):
        if self.shield_faces == 1.0: return self.shield_hp['Front']
        return sum(self.shield_hp.values())

    def update(self, dt):
        if self.is_destroyed: return
        
        for f in self.time_since_last_hit:
            self.time_since_last_hit[f] += dt
            
        self.time_since_last_dist_hit += dt 
        
        if self.shield_gen_dist_hp > 0:
            regen_amount = (self.total_regen_rate / self.shield_faces) * dt
            for f in self.shield_hp:
                if self.shield_hp[f] < self.max_shield_hp_per_face:
                    req_delay = self.shield_down_delay if self.shield_hp[f] <= 0.1 else self.shield_dmg_delay
                    if self.time_since_last_hit[f] >= req_delay:
                        self.shield_hp[f] = min(self.max_shield_hp_per_face, self.shield_hp[f] + regen_amount)
            
            if self.shield_faces == 1.0:
                base_val = self.shield_hp['Front']
                for f in self.shield_hp: self.shield_hp[f] = base_val
        
        if self.time_since_last_dist_hit >= self.pp_dist_decay_delay:
            if self.pp_dist_hp < self.max_pp_dist_hp:
                self.pp_dist_hp = min(self.max_pp_dist_hp, self.pp_dist_hp + (self.pp_dist_decay_rate * dt))

    def take_hit(self, weapon, hit_location='nose', attack_angle='Front'):
        if self.is_destroyed: return
        
        target_face = attack_angle
        
        if self.shield_faces == 1.0:
            for f in self.time_since_last_hit: self.time_since_last_hit[f] = 0.0
        else:
            self.time_since_last_hit[target_face] = 0.0
            
        d_in = weapon.alpha_damage
        dmg_type = weapon.damage_type
        
        current_face_hp = self.shield_hp[target_face]
        current_pp_depth = self.pp_depth_map.get(target_face, self.pp_depth)
        
        if dmg_type == 'distortion':
            self.time_since_last_dist_hit = 0.0
            
            if current_face_hp > 0 and self.shield_gen_dist_hp > 0:
                shield_ratio = current_face_hp / self.max_shield_hp_per_face if self.max_shield_hp_per_face > 0 else 0.0
                current_dist_res = self.shield_res_dist_min + ((self.shield_res_dist_max - self.shield_res_dist_min) * shield_ratio)
                d_active = d_in * (1.0 - current_dist_res)
                self.shield_gen_dist_hp -= d_active
                if self.shield_gen_dist_hp <= 0:
                    for f in self.shield_hp: self.shield_hp[f] = 0.0 
                return 
            else:
                d_pass = d_in 
                d_final = d_pass * self.hull_mod['distortion']
                actual_comp_dmg = d_final * self.pp_mod['distortion']
                self.pp_dist_hp -= actual_comp_dmg
                if self.pp_dist_hp <= 0:
                    self.is_destroyed = True
                    self.death_reason = "Ship Disabled (PP Distortion Shutdown)"
                return
                
        d_active = d_in * (1.0 - self.shield_resist.get(dmg_type, 0.0))
        
        if current_face_hp > 0:
            shield_ratio = current_face_hp / self.max_shield_hp_per_face if self.max_shield_hp_per_face > 0 else 0.0
            abs_min = self.shield_absorp_min[dmg_type]
            abs_max = self.shield_absorp_max[dmg_type]
            absorp_current = abs_min + (abs_max - abs_min) * shield_ratio
            d_shield_attempt = d_active * absorp_current
            d_shield_actual = min(d_shield_attempt, current_face_hp)
            
            self.shield_hp[target_face] -= d_shield_actual
            
            if self.shield_faces == 1.0:
                for f in self.shield_hp: self.shield_hp[f] = self.shield_hp[target_face]
            
            if dmg_type == 'energy':
                d_pass = d_active * (1.0 - absorp_current)
            else:
                d_pass = d_active - d_shield_actual
        else:
            d_pass = d_active

        if self.armor_hp > 0:
            armor_ratio = self.armor_hp / self.max_armor_hp if self.max_armor_hp > 0 else 1.0
            current_deflection = self.deflection[dmg_type] * armor_ratio
            if d_pass < current_deflection: return 

        d_final = d_pass * self.hull_mod[dmg_type]

        scale = (self.max_armor_hp - self.armor_hp) / self.max_armor_hp if self.max_armor_hp > 0 else 1.0
        # --- DIAGNOSTIC TRAP ---
        if actual_vital_part not in self.hull_parts:
            print(f"\n--- FATAL MISMATCH DETECTED ---")
            print(f"Target Ship: {getattr(self, 'name', 'Unknown')}")
            print(f"The engine is trying to hit: '{actual_vital_part}'")
            print(f"But the ONLY available hull parts are: {list(self.hull_parts.keys())}")
            print(f"The raw dictionary looks like this: {self.hull_parts}")
            print(f"-------------------------------\n")
            
        vital_dead = self.hull_parts[actual_vital_part]['hp'] <= 0

        comp_base = 0.0
        
        if vital_dead:
            comp_base = d_final
        else:
            current_pen = weapon.max_pen * scale
            if current_pen >= current_pp_depth: 
                current_comp_mod = self.comp_hull_mod * scale
                comp_base = d_final * current_comp_mod

        if comp_base > 0:
            actual_comp_dmg = comp_base * self.pp_mod[dmg_type]
            self.pp_hp -= actual_comp_dmg
            if self.pp_hp <= 0:
                self.is_destroyed = True
                if vital_dead:
                    self.death_reason = "PP Destroyed (Hull Breach Transfer)"
                else:
                    self.death_reason = f"PP Sniped (Armor Pen from {target_face})" 
                return 

        d_hull_taken = 0
        if self.armor_hp > 0:
            d_armor_taken = min(d_final, self.armor_hp)
            overflow = max(0, d_final - self.armor_hp)
            self.armor_hp -= d_armor_taken
            d_hull_taken = overflow
        else:
            d_hull_taken = d_final

        if d_hull_taken > 0 and not vital_dead:
            has_body = 'body' in self.hull_parts
            has_nose = 'nose' in self.hull_parts
            has_tail = 'tail' in self.hull_parts
            actual_vital_part = 'body'
            
            if target_face == 'Front':
                if has_nose: actual_vital_part = 'nose'
                elif has_body: actual_vital_part = 'body'
                elif has_tail: actual_vital_part = 'tail'
            elif target_face == 'Rear':
                if has_tail: actual_vital_part = 'tail'
                elif has_body: actual_vital_part = 'body'
                elif has_nose: actual_vital_part = 'nose'
            elif target_face in ['Left', 'Right']:
                if has_body:
                    actual_vital_part = 'body'
                elif has_nose and not has_tail:
                    actual_vital_part = 'nose'
                elif has_tail and not has_nose:
                    actual_vital_part = 'tail'
                elif has_nose and has_tail:
                    actual_vital_part = 'nose'
                    
            # Ultimate safety fallback
            if actual_vital_part not in self.hull_parts:
                actual_vital_part = list(self.hull_parts.keys())[0]

            # 1. Calculate actual damage and bleed (overflow)
            vital_hp = self.hull_parts[actual_vital_part]['hp']
            actual_hull_damage = min(d_hull_taken, max(0, vital_hp))
            hull_bleed = max(0, d_hull_taken - actual_hull_damage)

            # 2. Apply precise damage to the hull (this prevents the negative zero!)
            self.hull_parts[actual_vital_part]['hp'] -= actual_hull_damage

            # 3. Bleed excess damage directly into the Power Plant
            if hull_bleed > 0 and hasattr(self, 'pp_hp'):
                self.pp_hp -= hull_bleed
                if self.pp_hp <= 0:
                    self.is_destroyed = True
                    self.death_reason = "Power Plant Destroyed"

            # 4. Determine Death Condition
            if self.hull_parts[actual_vital_part]['hp'] <= 0 and not self.is_destroyed:
                # If the ship has a Power Plant, it survives hull destruction to absorb bleed!
                if not hasattr(self, 'pp_hp'): 
                    self.is_destroyed = True
                    self.death_reason = f"Hull Destroyed ({actual_vital_part.capitalize()})"

class AttackerFCS:
    def __init__(self, mode, weapons, target_ship, engagement_dist, db):
        self.mode = mode
        self.weapons = weapons
        self.target = target_ship
        self.distance = engagement_dist
        
        self.mistakes = 0
        self.was_shield_down = False
        self.is_firing_burst = False
        self.burst_timer = 0.0
        
        fastest_proj = max([w.speed for w in weapons]) if weapons else 1000.0
        self.flight_time = self.distance / fastest_proj if fastest_proj > 0 else 0.0

        if self.mode == "Human":
            target_shield_size = get_ship_shield_size(self.target.name, db)
            delays = []
            for s_data in db.shields.values():
                sz = DataTransformer.get_num(s_data.get('Shield_Size'), is_int=True)
                if sz == target_shield_size:
                    d = DataTransformer.get_num(s_data.get('Shield_Down_Delay'))
                    if d <= 0: d = DataTransformer.get_num(s_data.get('Regen_Delay', 5.0))
                    delays.append(d)
            
            avg_delay = sum(delays) / len(delays) if delays else 5.0
            base_assumed = float(int(avg_delay)) 
            self.assumed_delay = base_assumed + random.uniform(-1.5, 1.5)

    def process_trigger(self, dt):
        if self.mode == "Benchmark":
            return (True, False)

        elif self.mode == "Human":
            if self.is_firing_burst:
                self.burst_timer -= dt
                if self.burst_timer <= 0:
                    self.is_firing_burst = False
                return (True, True)
                
            # FIX: Monitor ANY damaged shield face, not just 0 HP faces
            damaged_faces = [f for f, hp in self.target.shield_hp.items() if hp < (self.target.max_shield_hp_per_face * 0.99)]
            
            is_currently_down = any(self.target.shield_hp[f] <= 0.1 for f in self.target.shield_hp)
            
            if self.was_shield_down and not is_currently_down:
                self.mistakes += 1
                exact_delay = self.target.shield_down_delay
                if self.mistakes == 1:
                    self.assumed_delay = exact_delay + random.uniform(-1.0, 1.0)
                else:
                    self.assumed_delay = exact_delay + random.uniform(-0.5, 0.5)
            
            self.was_shield_down = is_currently_down
            
            if damaged_faces:
                max_time_since_hit = max([self.target.time_since_last_hit[f] for f in damaged_faces])
                
                # If any damaged shield is about to regen, panic fire to keep it down
                if max_time_since_hit >= (self.assumed_delay - self.flight_time - 0.1):
                    cap_pcts = [w.current_ammo / w.cap_max for w in self.weapons if w.is_energy and w.cap_max > 0]
                    heat_pcts = [(w.current_heat / w.max_heat) for w in self.weapons if not w.is_energy and w.max_heat > 0]
                    
                    min_cap = min(cap_pcts) if cap_pcts else 1.0
                    max_heat = max(heat_pcts) if heat_pcts else 0.0
                    
                    if 0.02 <= min_cap <= 0.10 or 0.85 <= max_heat <= 0.95:
                        self.burst_timer = random.uniform(0.15, 0.25)
                    elif 0.10 < min_cap <= 0.25 or 0.70 <= max_heat < 0.85:
                        self.burst_timer = random.uniform(0.20, 0.80)
                    else:
                        self.burst_timer = random.uniform(0.3, 1.0)
                        
                    self.is_firing_burst = True
                    return (True, True) 
                else:
                    return (True, False) 
            else:
                return (True, False)

        elif self.mode == "AI":
            # FIX: Monitor ANY damaged shield face
            damaged_faces = [f for f, hp in self.target.shield_hp.items() if hp < (self.target.max_shield_hp_per_face * 0.99)]
            
            if damaged_faces:
                needs_override = False
                for f in damaged_faces:
                    # Use Down Delay if face is broken, otherwise use Dmg Delay
                    delay = self.target.shield_down_delay if self.target.shield_hp[f] <= 0.1 else self.target.shield_dmg_delay
                    
                    # If about to regen, force an override tap
                    if self.target.time_since_last_hit[f] >= (delay - self.flight_time - 0.05):
                        needs_override = True
                        break
                        
                if needs_override:
                    return (True, True)
                return (True, False)
                
            return (True, False)