import itertools
import collections
import concurrent.futures
import functools
import re
import os
from data_manager import GameDatabase, DataTransformer
from mechanics import DefenderLoadout, Weapon, Projectile, AttackerFCS

worker_db = None

def init_worker():
    global worker_db
    worker_db = GameDatabase()

def _evaluate_loadout(loadout_names, target_name, target_shield_name, target_pp_name, engagement_distance, trigger_logic, ammo_mod, regen_mod):
    global worker_db 
    target = DefenderLoadout(target_name, worker_db, target_pp_name)
    target.equip_shields(target_shield_name, worker_db)
    weapons = [Weapon(worker_db.weapons[name], ammo_mod, regen_mod) for name in loadout_names]
    speeds = [w.speed for w in weapons]
    speed_deviation = max(speeds) - min(speeds) if speeds else 0.0
    
    capable_weapons = 0
    for w in weapons:
        if w.damage_type == 'distortion':
            capable_weapons += 1 
            continue
        max_d_pass = w.alpha_damage * (1.0 - target.shield_resist.get(w.damage_type, 0.0))
        if target.armor_hp > 0 and max_d_pass < target.deflection.get(w.damage_type, 0.0):
            pass
        else:
            capable_weapons += 1
            
    if capable_weapons == 0:
        return {'loadout': loadout_names, 'ttk': float('inf'), 'reason': 'ALL WEAPONS DEFLECTED', 'speed_dev': speed_deviation}

    dt = 0.05 
    time_elapsed = 0.0
    active_projectiles = []
    
    fcs = AttackerFCS(trigger_logic, weapons, target, engagement_distance, worker_db)
    
    while not target.is_destroyed and time_elapsed < 600.0:
        trig_pulled, over_rech = fcs.process_trigger(dt)
        
        for w in weapons:
            if w.update(dt, trig_pulled, over_rech):
                active_projectiles.append(Projectile(w, engagement_distance))
                
        surviving_projectiles = []
        for proj in active_projectiles:
            if proj.update(dt):
                target.take_hit(proj.weapon, hit_location="nose")
            else:
                surviving_projectiles.append(proj)
        active_projectiles = surviving_projectiles
        
        target.update(dt)
        time_elapsed += dt
        
        ballistics = [w for w in weapons if not w.is_energy]
        if ballistics and all(w.total_ammo <= 0 for w in ballistics) and not any(w.is_energy for w in weapons) and not active_projectiles:
             return {'loadout': loadout_names, 'ttk': float('inf'), 'reason': 'OUT OF AMMO', 'speed_dev': speed_deviation}
             
    if target.is_destroyed:
        return {'loadout': loadout_names, 'ttk': time_elapsed, 'reason': target.death_reason, 'speed_dev': speed_deviation}
    else:
        return {'loadout': loadout_names, 'ttk': float('inf'), 'reason': 'TIME LIMIT EXCEEDED (Low DPS)', 'speed_dev': speed_deviation}

def generate_weapon_intel(unique_weapon_names, target_loadout, database):
    intel_report = []
    for w_name in unique_weapon_names:
        w_data = database.weapons.get(w_name)
        if not w_data: continue
        
        alpha = DataTransformer.get_num(w_data.get('Alpha_Dmg'))
        w_type = str(w_data.get('Weapon_Type', '')).lower()
        max_pen = DataTransformer.get_num(w_data.get('Pen_Distance'))
        
        if 'distortion' in w_type:
            dmg_type = 'distortion'
            armor_thresh = "N/A (Bypasses)"
            pp_thresh = "N/A (Bypasses)"
        else:
            dmg_type = 'ballistic' if 'ballistic' in w_type else 'energy'
            max_d_pass = alpha * (1.0 - target_loadout.shield_resist.get(dmg_type, 0.0))
            base_defl = target_loadout.deflection.get(dmg_type, 0.0)
            
            if base_defl == 0 or max_d_pass >= base_defl:
                armor_thresh = "100.0% (Pristine)"
            else:
                pct = (max_d_pass / base_defl) * 100.0
                armor_thresh = f"{pct:.1f}%"
                
            if max_pen >= target_loadout.pp_depth:
                pp_pct = (1.0 - (target_loadout.pp_depth / max_pen)) * 100.0
                pp_thresh = f"{pp_pct:.1f}%"
            else:
                pp_thresh = "Hull Breach Req"
            
        intel_report.append({
            "Weapon": DataTransformer.clean_weapon_name(w_name),
            "Type": dmg_type.capitalize(),
            "Bites Armor At": armor_thresh,
            "Strikes PP At": pp_thresh,
            "Max Pen (m)": max_pen
        })
    return intel_report

def run_tournament_engine(database, attacker_name, target_name, target_shield_name, target_pp_name=None, engagement_distance=1000.0, disallowed_terms=None, trigger_logic="Benchmark", min_penetration_pct=33.0, forced_weapons=None, min_ammo_speed=0.0, weapon_type_filter=None, homogeneous_grouping=False):
    if disallowed_terms is None: disallowed_terms = []
    if forced_weapons is None: forced_weapons = {}

    dummy_target = DefenderLoadout(target_name, database, target_pp_name)
    dummy_target.equip_shields(target_shield_name, database)
    
    ship_config = database.ship_configs.get(attacker_name, {})
    hardpoints = ship_config.get('hardpoints', [])
    if not hardpoints: return None, None, 0, 0, f"Error: No hardpoints found for {attacker_name}."
    
    ammo_mod = ship_config.get('max_ammo_mod', 1.0)
    regen_mod = ship_config.get('max_regen_sec_mod', 1.0)

    raw_bespoke_sizes = str(ship_config.get('Bespoke_Mount_Size', '')).split(',')
    bespoke_mount_sizes = [int(s.strip()) for s in raw_bespoke_sizes if s.strip().isdigit()]

    hp_counts = collections.Counter(hardpoints)
    weapons_by_size = {}
    tested_weapons_set = set() 
    
    def fetch_weapons_for_size(target_size, required_terms):
        valid_pre_speed = []
        for name, data in database.weapons.items():
            if DataTransformer.get_num(data.get('Weapon_Size'), is_int=True) != target_size: continue
            
            bespoke_tag = str(data.get('Bespoke_Ship', '')).strip().lower()
            is_bespoke_only_mount = target_size in bespoke_mount_sizes
            if is_bespoke_only_mount:
                if not bespoke_tag: continue
                allowed_ships = [s.strip() for s in bespoke_tag.split(',')]
                if not any(allowed in attacker_name.lower() for allowed in allowed_ships): continue
            else:
                if bespoke_tag:
                    allowed_ships = [s.strip() for s in bespoke_tag.split(',')]
                    if not any(allowed in attacker_name.lower() for allowed in allowed_ships): continue 

            w_type = str(data.get('Weapon_Type', '')).lower()
            w_name = name.lower()
            
            if 'distortion' in w_type: dmg_type = 'distortion'
            else: dmg_type = 'ballistic' if 'ballistic' in w_type else 'energy'
            
            if weapon_type_filter and weapon_type_filter.lower() != dmg_type: continue
            
            if disallowed_terms:
                if any(re.search(rf"\b{re.escape(t.lower())}", w_name) or re.search(rf"\b{re.escape(t.lower())}", w_type) for t in disallowed_terms):
                    continue
            
            if required_terms:
                if not any(re.search(rf"\b{re.escape(t.lower())}", w_name) or re.search(rf"\b{re.escape(t.lower())}", w_type) for t in required_terms):
                    continue
            
            if dmg_type != 'distortion':
                alpha_dmg = DataTransformer.get_num(data.get('Alpha_Dmg'))
                max_d_pass = alpha_dmg * (1.0 - dummy_target.shield_resist.get(dmg_type, 0.0))
                scaled_deflection = dummy_target.deflection.get(dmg_type, 0.0) * (min_penetration_pct / 100.0)
                if dummy_target.armor_hp > 0 and max_d_pass < scaled_deflection: continue
                
            ammo_speed = DataTransformer.get_num(data.get('Ammo_Speed'))
            valid_pre_speed.append((name, ammo_speed))
            
        fast_weapons = [name for name, speed in valid_pre_speed if speed >= min_ammo_speed]
        return fast_weapons if fast_weapons else [name for name, speed in valid_pre_speed]

    for size in hp_counts.keys():
        req_terms = forced_weapons.get(size, [])
        matched_weapons = fetch_weapons_for_size(size, req_terms)
        
        if not matched_weapons and req_terms:
            downsized_weapons = fetch_weapons_for_size(size - 1, req_terms)
            if downsized_weapons:
                matched_weapons = downsized_weapons 
                    
        if not matched_weapons:
            return None, None, 0, 0, f"No valid weapons found for Size {size} based on current filters."
            
        weapons_by_size[size] = matched_weapons
        tested_weapons_set.update(matched_weapons)

    size_combinations = []
    for size, count in hp_counts.items():
        pool = weapons_by_size[size]
        if forced_weapons.get(size) or homogeneous_grouping:
            combos = [tuple([weapon] * count) for weapon in pool]
        else:
            combos = list(itertools.combinations_with_replacement(pool, count))
        size_combinations.append(combos)

    unique_loadouts = []
    for combined in itertools.product(*size_combinations):
        flattened = [weapon for group in combined for weapon in group]
        unique_loadouts.append(flattened)
    
    total_combos = len(unique_loadouts)
    if total_combos == 0: return None, None, 0, 0, "No combinations generated."

    intel_data = generate_weapon_intel(tested_weapons_set, dummy_target, database)

    cpu_cores = os.cpu_count() or 4
    worker_func = functools.partial(
        _evaluate_loadout, target_name=target_name, target_shield_name=target_shield_name, target_pp_name=target_pp_name, engagement_distance=engagement_distance, trigger_logic=trigger_logic, ammo_mod=ammo_mod, regen_mod=regen_mod
    )
    
    results = []
    
    # --- MULTIPROCESSING ---
    with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_cores, initializer=init_worker) as executor:
        chunk = max(1, len(unique_loadouts) // (cpu_cores * 4))
        for res in executor.map(worker_func, unique_loadouts, chunksize=chunk):
            results.append(res)

    # --- RUN SINGLE-THREADED ---
    # init_worker() # Initialize any globals the worker normally needs
    # for loadout in unique_loadouts:
    #    res = worker_func(loadout)
    #    results.append(res)
        
    results.sort(key=lambda x: x['ttk'])
    return results, intel_data, dummy_target.pp_depth, total_combos, None

def simulate_visual_fight(attacker_1_weapons, attacker_2_weapons, target_ship, engagement_distance=1000.0, time_limit=600.0, trigger_1='Benchmark', trigger_2='Benchmark', angle_1='Front', angle_2='Front', db=None):
    dt = 0.05 
    time_elapsed = 0.0
    active_projectiles = []
    frames = []
    
    # --- NEW: COMBAT TELEMETRY LOG ---
    combat_log = []
    log_flags = {"first_hit": False, "shield_down": False, "armor_breached": False, "pp_hit": False}

    max_hull_hp = target_ship.hull_parts['body']['hp']
    if max_hull_hp <= 0: max_hull_hp = 1000.0
    
    spread_step = 25.0
    for atk_idx, wep_list in enumerate([attacker_1_weapons, attacker_2_weapons]):
        owner_id = atk_idx + 1
        start_x = -((len(wep_list) - 1) * spread_step) / 2.0
        for i, w in enumerate(wep_list):
            w.x_offset = start_x + (i * spread_step)
            w.owner = owner_id
            
    all_weapons = attacker_1_weapons + attacker_2_weapons
    
    fcs_1 = AttackerFCS(trigger_1, attacker_1_weapons, target_ship, engagement_distance, db)
    fcs_2 = AttackerFCS(trigger_2, attacker_2_weapons, target_ship, engagement_distance, db)
        
    while not target_ship.is_destroyed and time_elapsed < time_limit:
        trig1, over1 = fcs_1.process_trigger(dt)
        trig2, over2 = fcs_2.process_trigger(dt)
        
        for weapon in all_weapons:
            trigger = trig1 if weapon.owner == 1 else trig2
            over = over1 if weapon.owner == 1 else over2
            
            if weapon.update(dt, trigger, over):
                proj = Projectile(weapon, engagement_distance, weapon.x_offset)
                proj.owner = weapon.owner 
                active_projectiles.append(proj)
                
        surviving_projectiles = []
        impacts = [] 
        for proj in active_projectiles:
            if proj.update(dt):
                atk_ang = angle_1 if proj.owner == 1 else angle_2
                
                # --- NEW: Track pre-hit stats for the log ---
                pre_armor = target_ship.armor_hp
                pre_pp = target_ship.pp_hp
                pre_shield = target_ship.get_current_shield_hp()
                
                target_ship.take_hit(proj.weapon, attack_angle=atk_ang)
                p_type = 2 if proj.is_distortion else (1 if proj.is_energy else 0)
                impacts.append([round(proj.x_offset, 1), p_type, proj.owner])
                
                # --- NEW: POPULATE TELEMETRY LOG ---
                if not log_flags["first_hit"] and pre_shield == target_ship.max_total_shield_hp:
                    combat_log.append({"t": time_elapsed, "msg": f"First impact detected on {atk_ang} shield face.", "color": "#00c8ff"})
                    log_flags["first_hit"] = True
                    
                if not log_flags["shield_down"] and target_ship.get_current_shield_hp() <= 0.1 and pre_shield > 0.1:
                    combat_log.append({"t": time_elapsed, "msg": f"WARNING: {atk_ang} Shield face collapsed!", "color": "#ffaa00"})
                    log_flags["shield_down"] = True
                    
                if not log_flags["armor_breached"] and target_ship.armor_hp < pre_armor:
                    combat_log.append({"t": time_elapsed, "msg": f"Armor Deflection overcome. Hull taking physical damage.", "color": "#ffaa00"})
                    log_flags["armor_breached"] = True
                    
                if not log_flags["pp_hit"] and target_ship.pp_hp < pre_pp:
                    combat_log.append({"t": time_elapsed, "msg": f"CRITICAL: Armor penetrated. Power Plant taking direct damage!", "color": "#ff4444"})
                    log_flags["pp_hit"] = True
                    
            else:
                surviving_projectiles.append(proj)
        active_projectiles = surviving_projectiles
        
        target_ship.update(dt)
        
        armor_ratio = target_ship.armor_hp / target_ship.max_armor_hp if target_ship.max_armor_hp > 0 else 0.0
        cur_thresh_phys = target_ship.deflection['ballistic'] * armor_ratio
        cur_thresh_engy = target_ship.deflection['energy'] * armor_ratio

        sr_pcts = [1.0, 1.0, 1.0, 1.0]
        if target_ship.max_shield_hp_per_face > 0:
            faces = ['Front', 'Right', 'Rear', 'Left']
            for idx, face in enumerate(faces):
                if target_ship.shield_hp[face] < target_ship.max_shield_hp_per_face:
                    req_delay = target_ship.shield_down_delay if target_ship.shield_hp[face] <= 0.1 else target_ship.shield_dmg_delay
                    if req_delay > 0:
                        sr_pcts[idx] = min(1.0, target_ship.time_since_last_hit[face] / req_delay)

        dist_delay_pct = 1.0
        if target_ship.pp_dist_hp < target_ship.max_pp_dist_hp:
            dist_delay_pct = min(1.0, target_ship.time_since_last_dist_hit / target_ship.pp_dist_decay_delay)

        if target_ship.max_shield_hp_per_face > 0:
            face_pcts = [
                target_ship.shield_hp['Front'] / target_ship.max_shield_hp_per_face,
                target_ship.shield_hp['Right'] / target_ship.max_shield_hp_per_face,
                target_ship.shield_hp['Rear'] / target_ship.max_shield_hp_per_face,
                target_ship.shield_hp['Left'] / target_ship.max_shield_hp_per_face
            ]
            face_hps = [
                target_ship.shield_hp['Front'],
                target_ship.shield_hp['Right'],
                target_ship.shield_hp['Rear'],
                target_ship.shield_hp['Left']
            ]
        else:
            face_pcts = [0.0, 0.0, 0.0, 0.0]
            face_hps = [0.0, 0.0, 0.0, 0.0]

        arm_pct = armor_ratio
        pp_pct = target_ship.pp_hp / target_ship.max_pp_hp if target_ship.max_pp_hp > 0 else 0.0
        hull_pct = target_ship.hull_parts['body']['hp'] / max_hull_hp if max_hull_hp > 0 else 0.0
        
        proj_data = []
        for p in active_projectiles:
            p_type = 2 if p.is_distortion else (1 if p.is_energy else 0)
            proj_data.append([round(p.x_offset, 1), round(p.distance_remaining, 1), p_type, p.owner])
            
        def extract_wep_data(wep_list):
            w_data = []
            for w in wep_list:
                w_type = 2 if w.damage_type == 'distortion' else (1 if w.is_energy else 0)
                if w.is_energy:
                    w_data.append([w_type, round(w.current_ammo, 1), w.cap_max, w.is_recharging])
                else:
                    heat_pct = (w.current_heat / w.max_heat) * 100.0 if w.max_heat > 0 else 0.0
                    ammo_fired = w.initial_ammo - w.total_ammo
                    w_data.append([w_type, w.total_ammo, heat_pct, ammo_fired, w.is_overheated])
            return w_data
            
        frames.append({
            "t": round(time_elapsed, 2),
            "p": proj_data,
            "w1": extract_wep_data(attacker_1_weapons), 
            "w2": extract_wep_data(attacker_2_weapons), 
            "s": [round(max(0, p), 3) for p in face_pcts],
            "sr": [round(max(0, p), 3) for p in sr_pcts], 
            "a": round(max(0, arm_pct), 3),
            "atp": round(cur_thresh_phys, 1),
            "ate": round(cur_thresh_engy, 1),
            "sabp": [round((target_ship.shield_absorp_min['ballistic'] + (target_ship.shield_absorp_max['ballistic'] - target_ship.shield_absorp_min['ballistic']) * pct) * 100, 1) for pct in face_pcts],
            "sabd": [round((target_ship.shield_absorp_min['distortion'] + (target_ship.shield_absorp_max['distortion'] - target_ship.shield_absorp_min['distortion']) * pct) * 100, 1) for pct in face_pcts],
            "h": round(max(0, hull_pct), 3),
            "pp": round(max(0, pp_pct), 3),
            "pdh": round(max(0, target_ship.pp_dist_hp / target_ship.max_pp_dist_hp), 3),
            "pdr": round(dist_delay_pct, 3),
            "d": target_ship.is_destroyed,
            "i": impacts,
            "shp": [round(max(0, hp), 0) for hp in face_hps], 
            "mshp": round(target_ship.max_shield_hp, 0),
            "tshp": round(max(0, target_ship.get_current_shield_hp()), 0), 
            "ahp": round(max(0, target_ship.armor_hp), 0),                 
            "hhp": {k: v['hp'] for k, v in target_ship.hull_parts.items()},
            "hhp_max": {k: v['max_hp'] for k, v in target_ship.hull_parts.items()},
            "pphp": round(max(0, target_ship.pp_hp), 0)                    
        })
        
        time_elapsed += dt
        
        ballistics = [w for w in all_weapons if not w.is_energy]
        if ballistics and all(w.total_ammo <= 0 for w in ballistics) and not any(w.is_energy for w in all_weapons) and not active_projectiles:
             break
             
    return frames, time_elapsed, target_ship.death_reason, combat_log