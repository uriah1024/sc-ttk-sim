import os
import csv
import itertools
import collections
import concurrent.futures
import functools
import time 
import re 
import json
import base64
import random
import streamlit as st
import pandas as pd
import altair as alt
import streamlit.components.v1 as components

st.set_page_config(page_title="SC TTK Simulator", layout="wide", initial_sidebar_state="collapsed")

# --- GLOBAL CSS OVERRIDES ---
st.markdown("""
    <style>
    /* Match Tab Font Size to Subheaders */
    button[data-baseweb="tab"] {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
    }
    
    /* Hollow Interactive Reset Button Styling */
    button[kind="secondary"] {
        border: 1px solid #4a4a5a !important;
        background-color: transparent !important;
        color: #aaaaaa !important;
        transition: all 0.15s ease-in-out !important;
    }
    button[kind="secondary"]:hover {
        background-color: #3a3a4a !important;
        border-color: #888899 !important;
        color: #ffffff !important;
    }
    button[kind="secondary"]:active {
        background-color: #ff4b4b !important;
        border-color: #ff4b4b !important;
        color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. DATA TRANSFORMATION & LOADING
# ==========================================

class DataTransformer:
    @staticmethod
    def get_multiplier(raw_value):
        if not raw_value: return 1.0
        return float(raw_value)

    @staticmethod
    def get_num(val, is_int=False):
        if val is None or val == '': return 0 if is_int else 0.0
        
        val_str = str(val).strip().replace(',', '')
        if val_str == '∞': return 999999 if is_int else 999999.0
        
        match = re.search(r'[-+]?\d*\.?\d+', val_str)
        if match:
            try:
                parsed = float(match.group())
                return int(parsed) if is_int else parsed
            except ValueError:
                pass
        return 0 if is_int else 0.0

    @staticmethod
    def clean_weapon_name(name):
        terms_to_remove = [
            ' Laser', ' Ballistic', ' Distortion', ' Electron', ' Neutron', ' Plasma', ' Tachyon',
            ' Repeater', ' Cannon', ' Gatling', ' Scattergun', ' Mass Driver', ' Autocannon', ' Blaster', ' Gun'
        ]
        cleaned = str(name)
        for term in terms_to_remove:
            cleaned = re.sub(term, '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

class GameDatabase:
    def __init__(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.ships = self._load_csv(os.path.join(script_dir, 'ships.csv'), 'Ship_Name')
        self.shields = self._load_csv(os.path.join(script_dir, 'shields.csv'), 'Shield_Name')
        self.weapons = self._load_csv(os.path.join(script_dir, 'weapons.csv'), 'Weapon_Name')
        self.ship_configs = self._load_ship_configs(os.path.join(script_dir, 'ship_configs.csv'))
        
        self.power_plants = self._load_csv(os.path.join(script_dir, 'power_plants.csv'), 'PP_Name')
        self.ship_pp_configs = self._load_csv(os.path.join(script_dir, 'ship_power_distance.csv'), 'Ship_Name_PP_Key')

    def _load_csv(self, filepath, key_col_name):
        data = {}
        if not os.path.exists(filepath): return data 
        
        with open(filepath, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [str(col).strip().lstrip('\ufeff') for col in reader.fieldnames]
                
            for row in reader:
                key = row.get(key_col_name)
                if key:
                    data[key] = row
        return data

    def _load_ship_configs(self, filepath):
        configs = {}
        if not os.path.exists(filepath): return configs
        with open(filepath, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [str(col).strip().lstrip('\ufeff') for col in reader.fieldnames]
                
            for row in reader:
                name = row.get('Name')
                if not name or row.get('Type') != 'Ship': continue
                
                hardpoints = []
                for size in range(1, 11):
                    count = DataTransformer.get_num(row.get(f'Weapon_Size_{size}'), is_int=True)
                    for _ in range(count):
                        hardpoints.append(size)
                
                configs[name] = {
                    'shield_count': DataTransformer.get_num(row.get('Shield_Count'), is_int=True),
                    'ship_shield_size': DataTransformer.get_num(row.get('Ship_Shield_Size'), is_int=True),
                    'nose_hp': DataTransformer.get_num(row.get('Vital_Nose_Hull_HP')),
                    'body_hp': DataTransformer.get_num(row.get('Vital_Body_Hull_HP')),
                    'tail_hp': DataTransformer.get_num(row.get('Vital_Tail_Hull_HP')),
                    'Bespoke_Mount_Size': row.get('Bespoke_Mount_Size', ''),
                    'hardpoints': hardpoints,
                    'max_ammo_mod': DataTransformer.get_num(row.get('Max_Ammo_Mod')),
                    'max_regen_sec_mod': DataTransformer.get_num(row.get('Max_Regen_Sec_Mod'))
                }
        return configs


# ==========================================
# 2. SMART COMPONENT DEFAULTS
# ==========================================

def get_ship_shield_size(ship_name, db):
    sz = db.ship_configs.get(ship_name, {}).get('ship_shield_size', 0)
    if sz > 0: return sz
    ship_data = db.ships.get(ship_name, {})
    sz = DataTransformer.get_num(ship_data.get('Shield_Size', ship_data.get('Max_Shield_Size', 0)), is_int=True)
    return max(1, sz)

def get_ship_pp_size(ship_name, db):
    sz = DataTransformer.get_num(db.ship_pp_configs.get(ship_name, {}).get('PP_Comp_Size', 0), is_int=True)
    if sz > 0: return sz
    ship_data = db.ships.get(ship_name, {})
    sz = DataTransformer.get_num(ship_data.get('PP_Comp_Size', ship_data.get('PP_Size', 0)), is_int=True)
    return max(1, sz)

def get_default_shield(ship_name, db):
    size = get_ship_shield_size(ship_name, db)
    if size == 1: return "FR-66"
    elif size == 2: return "FR-76"
    elif size >= 3: return "FR-86"
    return "FR-66"

def get_default_pp(ship_name, db):
    size = get_ship_pp_size(ship_name, db)
    pp_config = db.ship_pp_configs.get(ship_name, {})
    def_comp = pp_config.get('Default_PP_Component', '')
    if def_comp: return def_comp
    
    if size == 1: return "JS-300"
    elif size == 2: return "JS-400"
    elif size >= 3: return "JS-500"
    return "JS-300"

def render_target_components(tab_prefix, target_ship_name, db):
    if 'ship_prefs' not in st.session_state:
        st.session_state.ship_prefs = {}
        
    req_shd_size = get_ship_shield_size(target_ship_name, db)
    req_pp_size = get_ship_pp_size(target_ship_name, db)
    
    valid_shields = []
    for n, d in db.shields.items():
        sz = DataTransformer.get_num(d.get('Shield_Size'), is_int=True)
        if sz in (req_shd_size, 0): valid_shields.append(n)
            
    valid_pps = []
    for n, d in db.power_plants.items():
        sz = DataTransformer.get_num(d.get('PP_Size', d.get('Size', d.get('PP_Comp_Size', 0))), is_int=True)
        if sz in (req_pp_size, 0): valid_pps.append(n)
            
    valid_shields = ["None"] + sorted(valid_shields)
    valid_pps = ["Default"] + sorted(valid_pps)

    def_shd = get_default_shield(target_ship_name, db)
    if def_shd not in valid_shields and len(valid_shields) > 1: def_shd = valid_shields[1]
    
    def_pp = get_default_pp(target_ship_name, db)
    if def_pp not in valid_pps and len(valid_pps) > 1: def_pp = valid_pps[1]
    
    prefs = st.session_state.ship_prefs.get(target_ship_name, {})
    cur_shd = prefs.get('shield', def_shd)
    cur_pp = prefs.get('pp', def_pp)
    
    shd_key = f"{tab_prefix}_shd"
    pp_key = f"{tab_prefix}_pp"
    last_ship_key = f"{tab_prefix}_last_ship"
    
    if st.session_state.get(last_ship_key) != target_ship_name:
        st.session_state[shd_key] = cur_shd if cur_shd in valid_shields else def_shd
        st.session_state[pp_key] = cur_pp if cur_pp in valid_pps else def_pp
        st.session_state[last_ship_key] = target_ship_name
        
    if st.session_state.get(shd_key) not in valid_shields: st.session_state[shd_key] = def_shd
    if st.session_state.get(pp_key) not in valid_pps: st.session_state[pp_key] = def_pp
    
    selected_shd = st.selectbox("Target Shield", valid_shields, key=shd_key)
    selected_pp = st.selectbox("Target Power Plant", valid_pps, key=pp_key)
        
    if target_ship_name not in st.session_state.ship_prefs:
        st.session_state.ship_prefs[target_ship_name] = {}
    st.session_state.ship_prefs[target_ship_name]['shield'] = selected_shd
    st.session_state.ship_prefs[target_ship_name]['pp'] = selected_pp
    
    return selected_shd, selected_pp

def reset_tab_defaults(tab_prefix, target_ship_key):
    target_ship = st.session_state[target_ship_key]
    req_shd_size = get_ship_shield_size(target_ship, db)
    req_pp_size = get_ship_pp_size(target_ship, db)
    
    valid_shields = []
    for n, d in db.shields.items():
        sz = DataTransformer.get_num(d.get('Shield_Size'), is_int=True)
        if sz in (req_shd_size, 0): valid_shields.append(n)
            
    valid_pps = []
    for n, d in db.power_plants.items():
        sz = DataTransformer.get_num(d.get('PP_Size', d.get('Size', d.get('PP_Comp_Size', 0))), is_int=True)
        if sz in (req_pp_size, 0): valid_pps.append(n)
            
    valid_shields = ["None"] + sorted(valid_shields)
    valid_pps = ["Default"] + sorted(valid_pps)
    
    def_shd = get_default_shield(target_ship, db)
    if def_shd not in valid_shields and len(valid_shields) > 1: def_shd = valid_shields[1]
    
    def_pp = get_default_pp(target_ship, db)
    if def_pp not in valid_pps and len(valid_pps) > 1: def_pp = valid_pps[1]
    
    st.session_state[f"{tab_prefix}_shd"] = def_shd
    st.session_state[f"{tab_prefix}_pp"] = def_pp
    
    if 'ship_prefs' in st.session_state and target_ship in st.session_state.ship_prefs:
        st.session_state.ship_prefs[target_ship]['shield'] = def_shd
        st.session_state.ship_prefs[target_ship]['pp'] = def_pp

# ==========================================
# 3. MECHANICS: WEAPONS & PROJECTILES
# ==========================================

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
                elif override_recharge and trigger_pulled:
                    local_trigger = True
                    self.is_recharging = False 
            else:
                local_trigger = trigger_pulled
                if self.current_ammo < 1 and local_trigger:
                    self.is_recharging = True 
                    local_trigger = False

            if not local_trigger:
                self.time_since_last_shot = min(self.time_since_last_shot, self.time_between_shots)

            if local_trigger:
                self.time_since_trigger_released = 0.0 
                if self.time_since_last_shot >= self.time_between_shots and self.current_ammo >= 1:
                    self.current_ammo -= 1
                    self.time_since_last_shot -= self.time_between_shots 
                    fired = True
                    if self.current_ammo < 1:
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


# ==========================================
# 4. MECHANICS: LOADOUTS & SHIPS
# ==========================================

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
        
        self.hull_parts['body'] = {'hp': body_hp if body_hp > 0 else 1000, 'parent': None, 'transfer_rate': 0.0, 'is_vital': True}
        if nose_hp > 0:
            self.hull_parts['nose'] = {'hp': nose_hp, 'parent': 'body', 'transfer_rate': 1.0, 'is_vital': False}

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
        vital_dead = self.hull_parts['body']['hp'] <= 0

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
            loc = hit_location if hit_location in self.hull_parts else 'body'
            damage_to_propagate = d_hull_taken

            while loc and damage_to_propagate > 0:
                part = self.hull_parts[loc]
                actual_part_damage = min(damage_to_propagate, part['hp'])
                part['hp'] -= actual_part_damage
                if part['parent']:
                    if part['hp'] <= 0:
                        damage_to_propagate = max(0, damage_to_propagate - actual_part_damage)
                    else:
                        damage_to_propagate = damage_to_propagate * part['transfer_rate']
                    loc = part['parent']
                else:
                    break


# ==========================================
# 5. SIMULATION ENGINES
# ==========================================

worker_db = None

def init_worker():
    global worker_db
    worker_db = GameDatabase()

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
                
            shield_is_down = any(hp <= 0.1 for hp in self.target.shield_hp.values())
            
            if self.was_shield_down and not shield_is_down:
                self.mistakes += 1
                exact_delay = self.target.shield_down_delay
                if self.mistakes == 1:
                    self.assumed_delay = exact_delay + random.uniform(-1.0, 1.0)
                else:
                    self.assumed_delay = exact_delay + random.uniform(-0.5, 0.5)
            
            self.was_shield_down = shield_is_down
            
            if shield_is_down:
                down_faces = [f for f, hp in self.target.shield_hp.items() if hp <= 0.1]
                max_time_since_hit = max([self.target.time_since_last_hit[f] for f in down_faces]) if down_faces else 0.0
                
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
                    return (False, False) 
            else:
                return (True, False)

        elif self.mode == "AI":
            shield_is_down = any(hp <= 0.1 for hp in self.target.shield_hp.values())
            if shield_is_down:
                down_faces = [f for f, hp in self.target.shield_hp.items() if hp <= 0.1]
                max_time_since_hit = max([self.target.time_since_last_hit[f] for f in down_faces]) if down_faces else 0.0
                if max_time_since_hit >= (self.target.shield_down_delay - self.flight_time - 0.05):
                    return (True, True)
                return (False, False)
            return (True, False)
            
        return (True, False) 

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
    with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_cores, initializer=init_worker) as executor:
        chunk = max(1, len(unique_loadouts) // (cpu_cores * 4))
        for res in executor.map(worker_func, unique_loadouts, chunksize=chunk):
            results.append(res)
        
    results.sort(key=lambda x: x['ttk'])
    return results, intel_data, dummy_target.pp_depth, total_combos, None


# --- UPDATED FLEET MODE VISUALIZER ENGINE ---
def simulate_visual_fight(attacker_1_weapons, attacker_2_weapons, target_ship, engagement_distance=1000.0, time_limit=600.0, trigger_1='Benchmark', trigger_2='Benchmark', angle_1='Front', angle_2='Front', db=None):
    dt = 0.05 
    time_elapsed = 0.0
    active_projectiles = []
    frames = []
    
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
                target_ship.take_hit(proj.weapon, attack_angle=atk_ang)
                p_type = 2 if proj.is_distortion else (1 if proj.is_energy else 0)
                impacts.append([round(proj.x_offset, 1), p_type, proj.owner])
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
                if w.is_energy:
                    w_data.append([1, round(w.current_ammo, 1), w.cap_max, w.is_recharging])
                else:
                    heat_pct = (w.current_heat / w.max_heat) * 100.0 if w.max_heat > 0 else 0.0
                    ammo_fired = w.initial_ammo - w.total_ammo
                    w_data.append([0, w.total_ammo, heat_pct, ammo_fired, w.is_overheated])
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
            "hhp": round(max(0, target_ship.hull_parts['body']['hp']), 0), 
            "pphp": round(max(0, target_ship.pp_hp), 0)                    
        })
        
        time_elapsed += dt
        
        ballistics = [w for w in all_weapons if not w.is_energy]
        if ballistics and all(w.total_ammo <= 0 for w in ballistics) and not any(w.is_energy for w in all_weapons) and not active_projectiles:
             break
             
    return frames, time_elapsed, target_ship.death_reason

# ==========================================
# 6. UI HELPERS
# ==========================================

def generate_discord_copy_button(dataframe, button_text):
    headers = list(dataframe.columns)
    md_lines = [f"| {' | '.join(headers)} |", "|" + "|".join(["---"]*len(headers)) + "|"]
    for _, row in dataframe.iterrows():
        md_lines.append(f"| {' | '.join([str(row[h]) for h in headers])} |")
    
    discord_md = "\n".join(md_lines)
    b64_md = base64.b64encode(discord_md.encode('utf-8')).decode('utf-8')
    
    html = f"""
    <button onclick="navigator.clipboard.writeText(atob('{b64_md}')); this.innerText='Copied!'; setTimeout(()=>this.innerText='{button_text}', 2000);" 
    style="background-color: #5865F2; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-family: sans-serif; font-weight: bold; margin-bottom: 10px;">
    {button_text}
    </button>
    """
    components.html(html, height=40)

def generate_interactive_ttk_chart(df, title):
    plot_df = df[df["TTK Float"] != float('inf')].copy()
    if plot_df.empty: return
    
    plot_df = plot_df.sort_values('TTK Float')
    
    chart = alt.Chart(plot_df).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X('TTK Float:Q', title='Time to Kill (Seconds)'),
        y=alt.Y('Loadout:N', sort=alt.EncodingSortField(field='TTK Float', order='ascending'), title=None, axis=alt.Axis(labelLimit=300)),
        color=alt.Color('TTK Float:Q', scale=alt.Scale(scheme='tealblues', reverse=True), legend=None),
        tooltip=['Loadout', 'TTK', 'Velocity Dev', 'Death Reason']
    ).properties(
        title=title,
        height=min(400, max(150, len(plot_df) * 40))
    )
    st.altair_chart(chart, use_container_width=True)

# ==========================================
# 7. STREAMLIT GUI FRONTEND
# ==========================================

if __name__ == '__main__':
    st.title("🚀 Star Citizen TTK Simulator")

    @st.cache_data
    def load_db():
        return GameDatabase()

    db = load_db()

    if not db.ships or not db.weapons:
        st.error("Missing CSV files! Ensure ships.csv, weapons.csv, etc., are in the same folder.")
        st.stop()
    
    attacker_options = sorted(list(db.ships.keys()))
    defender_options = sorted(list(db.ships.keys()))

    tab_tourney, tab_sandbox, tab_visualizer = st.tabs(["🏆 Tournament Engine", "🔬 Penetration Sandbox", "🎬 Combat Visualizer"])
    
    trigger_help = "Benchmark: Waits for full capacity.\nHuman: Estimates shield regen delays with human error margins.\nAI: Uses perfect math/distance tracking to keep shields down."
    
    # === TAB 1: TOURNAMENT ENGINE ===
    with tab_tourney:
        col_t1_setup, col_t1_main = st.columns([1, 4], gap="large")
        
        with col_t1_setup:
            st.subheader("⚙️ Match Setup")
            t1_attacker = st.selectbox("Attacker Ship", attacker_options, index=attacker_options.index("F7A Hornet Mk II") if "F7A Hornet Mk II" in attacker_options else 0, key="t1_atk")
            t1_target = st.selectbox("Target Ship", defender_options, index=defender_options.index("Arrow") if "Arrow" in defender_options else 0, key="t1_tgt")
            
            t1_shield, t1_pp = render_target_components("t1", t1_target, db)
            
            t1_dist = st.number_input("Engagement Distance (m)", value=500.0, step=100.0, key="t1_dst")
            
            run_btn = st.button("🚀 Run Tournament Simulator", type="primary", use_container_width=True)
            st.button("↺ Reset Defaults", key="rst_t1", use_container_width=True, on_click=reset_tab_defaults, args=("t1", "t1_tgt"))
            
            st.divider()
            
            st.subheader("Rules & Filters")
            t1_trigger = st.selectbox("Trigger Logic", ["Benchmark", "Human", "AI"], help=trigger_help, key="t1_trig")
            t1_force = st.checkbox("Force Identical Sized Weapons", value=True, key="t1_frc")
            t1_dmg = st.selectbox("Damage Preference", ["Any", "Energy", "Ballistic", "Distortion"], key="t1_dmg")
            t1_vel = st.number_input("Velocity Floor (m/s)", value=0.0, step=100.0, key="t1_vel")
            t1_armor = st.number_input("Min Pen Armor Cutoff (%)", value=0.0, step=10.0, key="t1_arm")
            t1_banned = st.text_input("Banned Terms (Comma Separated)", value="scattergun, mass driver", key="t1_ban")
            t1_whitelist = st.text_input("Force Weapons (e.g., 3:Panther)", key="t1_whi")
            
            banned_list = [x.strip() for x in t1_banned.split(',')] if t1_banned else []
            whitelist_dict = {}
            if t1_whitelist:
                for pair in t1_whitelist.split(','):
                    if ':' in pair:
                        try:
                            sz_str, name_str = pair.split(':', 1)
                            whitelist_dict[int(sz_str.strip())] = [name_str.strip()]
                        except ValueError:
                            pass

        with col_t1_main:
            if run_btn:
                actual_pp = None if t1_pp == "Default" else t1_pp
                actual_shield = None if t1_shield == "None" else t1_shield
                dmg_val = None if t1_dmg == "Any" else t1_dmg.lower()
                
                with st.spinner("Calculating combinations... Engaging Warp Drive..."):
                    start_time = time.time()
                    results, intel, pp_depth, total_combos, err = run_tournament_engine(
                        database=db, attacker_name=t1_attacker, target_name=t1_target, 
                        target_shield_name=actual_shield, target_pp_name=actual_pp, 
                        engagement_distance=t1_dist, disallowed_terms=banned_list, 
                        trigger_logic=t1_trigger, min_penetration_pct=t1_armor, 
                        forced_weapons=whitelist_dict, min_ammo_speed=t1_vel, 
                        weapon_type_filter=dmg_val, homogeneous_grouping=t1_force
                    )
                    elapsed = time.time() - start_time
                    
                if err:
                    st.error(err)
                else:
                    st.success(f"Simulation complete! Evaluated {total_combos:,} loadouts in {elapsed:.2f} seconds.")
                    
                    df_data = []
                    for r in results:
                        ttk_val = f"{r['ttk']:.2f}s" if r['ttk'] != float('inf') else "FAILED"
                        counts = collections.Counter(r['loadout'])
                        pretty_loadout = ", ".join([f"{v}x {DataTransformer.clean_weapon_name(k)}" for k, v in counts.items()])
                        
                        df_data.append({
                            "TTK": ttk_val,
                            "Death Reason": r['reason'],
                            "Velocity Dev": f"{r['speed_dev']:.0f} m/s",
                            "Loadout": pretty_loadout,
                            "Speed Float": r['speed_dev'], 
                            "TTK Float": r['ttk']
                        })
                    
                    df = pd.DataFrame(df_data)
                    
                    st.subheader("🏆 Top Loadouts (Overall)")
                    top_10_df = df.drop(columns=["Speed Float"]).head(10)
                    generate_interactive_ttk_chart(top_10_df, "Overall TTK Breakdown")
                    generate_discord_copy_button(top_10_df.drop(columns=["TTK Float"]), "📋 Copy Top 10 to Discord")
                    st.dataframe(top_10_df.drop(columns=["TTK Float"]), use_container_width=True, hide_index=True)
                    
                    st.subheader("🏆 Top Loadouts (Velocity Matched < 60 m/s)")
                    matched_df = df[df["Speed Float"] < 60.0]
                    if matched_df.empty:
                        st.info("No loadouts found with a velocity deviation under 60 m/s.")
                    else:
                        top_10_matched = matched_df.drop(columns=["Speed Float"]).head(10)
                        generate_interactive_ttk_chart(top_10_matched, "Velocity Matched TTK Breakdown")
                        generate_discord_copy_button(top_10_matched.drop(columns=["TTK Float"]), "📋 Copy Matched Top 10 to Discord")
                        st.dataframe(top_10_matched.drop(columns=["TTK Float"]), use_container_width=True, hide_index=True)
                    
                    st.divider()
    
                    st.subheader("📊 Weapon Intelligence Report")
                    intel_df = pd.DataFrame(intel)
                    generate_discord_copy_button(intel_df, "📋 Copy Intel to Discord")
                    st.dataframe(intel_df, use_container_width=True, hide_index=True)
            else:
                st.info("Configure your matchup on the left and click 'Run Tournament Simulator' to begin.")

    # === TAB 2: PENETRATION SANDBOX ===
    with tab_sandbox:
        col_t2_setup, col_t2_main = st.columns([1, 4], gap="large")
        
        with col_t2_setup:
            st.subheader("⚙️ Match Setup")
            t2_target = st.selectbox("Target Ship", defender_options, index=defender_options.index("Arrow") if "Arrow" in defender_options else 0, key="t2_tgt")
            t2_shield, t2_pp = render_target_components("t2", t2_target, db)
            
            st.button("↺ Reset Defaults", key="rst_t2", use_container_width=True, on_click=reset_tab_defaults, args=("t2", "t2_tgt"))

            st.divider()
            st.subheader("Test Parameters")
            sandbox_weapon_name = st.selectbox("Detail Test Weapon", sorted(list(db.weapons.keys())))
            sandbox_shield_pct = st.slider("Current Shield %", 0.0, 100.0, 100.0, step=1.0)
            sandbox_armor_pct = st.slider("Current Armor %", 0.0, 100.0, 100.0, step=1.0)
            t2_attacker = st.selectbox("Attacker Ship (For Fleet Chart)", attacker_options, index=attacker_options.index("F7A Hornet Mk II") if "F7A Hornet Mk II" in attacker_options else 0, key="t2_atk")

        with col_t2_main:
            st.header("Interactive Penetration Sandbox")
            st.write("Adjust the target's remaining Shield and Armor % on the left to visualize exactly when weapons will overcome deflection and breach the Power Plant depth.")
            
            sb_target = DefenderLoadout(t2_target, db, None if t2_pp == "Default" else t2_pp)
            sb_target.equip_shields(None if t2_shield == "None" else t2_shield, db)
            
            sb_weapon = Weapon(db.weapons[sandbox_weapon_name], 1.0, 1.0)
            
            if sb_weapon.damage_type == 'distortion':
                st.warning("Distortion weapons bypass physical geometry completely and attack the shield generator directly.")
            else:
                shield_ratio = sandbox_shield_pct / 100.0
                d_active = sb_weapon.alpha_damage * (1.0 - sb_target.shield_resist.get(sb_weapon.damage_type, 0.0))
                
                if shield_ratio > 0 and sb_target.max_shield_hp > 0:
                    abs_min = sb_target.shield_absorp_min[sb_weapon.damage_type]
                    abs_max = sb_target.shield_absorp_max[sb_weapon.damage_type]
                    absorp_current = abs_min + (abs_max - abs_min) * shield_ratio
                    d_pass = d_active * (1.0 - absorp_current)
                else:
                    d_pass = d_active
                    
                current_armor_ratio = sandbox_armor_pct / 100.0
                current_deflection = sb_target.deflection.get(sb_weapon.damage_type, 0.0) * current_armor_ratio
                
                scale = 1.0 - current_armor_ratio
                current_pen_depth = sb_weapon.max_pen * scale
                pp_target_depth = sb_target.pp_depth
                
                bites_armor = d_pass >= current_deflection
                strikes_pp = current_pen_depth >= pp_target_depth
                
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric(f"{DataTransformer.clean_weapon_name(sandbox_weapon_name)} vs Deflection", 
                              f"{d_pass:.1f} dmg vs {current_deflection:.1f} defl", 
                              "Deflected" if not bites_armor else "Bites Armor",
                              delta_color="inverse" if not bites_armor else "normal")
                with col_res2:
                    st.metric("Penetration vs PP Depth", 
                              f"{current_pen_depth:.2f}m / {pp_target_depth:.2f}m",
                              "Sniped" if strikes_pp else "Too Shallow",
                          delta_color="normal" if strikes_pp else "inverse")
                    
                st.markdown("### Individual Depth Visualizer")
                
                visual_max = max(sb_weapon.max_pen, pp_target_depth) * 1.1
                if visual_max == 0: visual_max = 1.0
                
                pen_fill_pct = (current_pen_depth / visual_max) * 100.0
                pp_marker_pct = (pp_target_depth / visual_max) * 100.0
                bar_color = "#00cc44" if strikes_pp else "#0088ff"
                
                custom_html = f"""
                <div style="width: 100%; max-width: 800px; background-color: #2b2b36; height: 40px; position: relative; border-radius: 5px; overflow: hidden; border: 1px solid #555;">
                   <div style="position: absolute; left: 0; top: 0; height: 100%; width: {pen_fill_pct}%; background-color: {bar_color}; border-radius: 5px 0 0 5px; transition: width 0.3s ease;"></div>
                   <div style="position: absolute; left: {pp_marker_pct}%; top: 0; height: 100%; width: 4px; background-color: #ff3333; z-index: 10;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; max-width: 800px; font-size: 12px; color: #aaa; margin-top: 5px;">
                    <span>0m (Hull Exterior)</span>
                    <span>Power Plant Depth: <span style="color: #ff3333; font-weight: bold;">{pp_target_depth:.2f}m</span></span>
                    <span>Max Visual Depth: {visual_max:.1f}m</span>
                </div>
                """
                st.markdown(custom_html, unsafe_allow_html=True)
                
                if strikes_pp:
                    st.success(f"💥 At {sandbox_armor_pct}% Armor, the {DataTransformer.clean_weapon_name(sandbox_weapon_name)} breaches {current_pen_depth:.2f}m deep, successfully striking the Power Plant.")
                else:
                    st.warning(f"🛡️ At {sandbox_armor_pct}% Armor, the {DataTransformer.clean_weapon_name(sandbox_weapon_name)} only penetrates {current_pen_depth:.2f}m. You must lower the armor further to reach the {pp_target_depth:.2f}m target.")
    
            st.divider()
            st.markdown(f"### Fleet-Wide Penetration Potential for {t2_attacker}")
            
            attacker_sizes = set(db.ship_configs[t2_attacker].get('hardpoints', []))
            chart_data = []
            
            for w_name, w_data in db.weapons.items():
                w = Weapon(w_data, 1.0, 1.0)
                if w.size not in attacker_sizes: continue
                if w.damage_type == 'distortion': continue 
                
                c_d_active = w.alpha_damage * (1.0 - sb_target.shield_resist.get(w.damage_type, 0.0))
                if shield_ratio > 0 and sb_target.max_shield_hp > 0:
                    c_abs_min = sb_target.shield_absorp_min[w.damage_type]
                    c_abs_max = sb_target.shield_absorp_max[w.damage_type]
                    c_absorp_current = c_abs_min + (c_abs_max - c_abs_min) * shield_ratio
                    c_d_pass = c_d_active * (1.0 - c_absorp_current)
                else:
                    c_d_pass = c_d_active
                    
                c_current_deflection = sb_target.deflection.get(w.damage_type, 0.0) * current_armor_ratio
                c_bites_armor = c_d_pass >= c_current_deflection
                c_current_pen = (w.max_pen * scale) if c_bites_armor else 0.0
                
                chart_data.append({
                    "Weapon": DataTransformer.clean_weapon_name(w_name),
                    "Current Pen (m)": round(c_current_pen, 2),
                    "Type": w.damage_type.capitalize(),
                    "Bites Armor": c_bites_armor
                })
                
            chart_df = pd.DataFrame(chart_data)
            if not chart_df.empty:
                base = alt.Chart(chart_df).encode(
                    y=alt.Y('Weapon:N', sort='-x', title=None)
                )
                bars = base.mark_bar().encode(
                    x=alt.X('Current Pen (m):Q', title=f'Current Penetration Depth at {sandbox_armor_pct}% Armor'),
                    color=alt.Color('Type:N', scale=alt.Scale(domain=['Ballistic', 'Energy'], range=['#ffaa00', '#00ffff'])),
                    tooltip=['Weapon', 'Type', 'Current Pen (m)', 'Bites Armor']
                )
                rule = alt.Chart(pd.DataFrame({'x': [pp_target_depth]})).mark_rule(color='#ff3333', strokeWidth=3, strokeDash=[5, 5]).encode(x='x:Q')
                st.altair_chart((bars + rule).properties(height=max(150, len(chart_df)*30)), use_container_width=True)

    # === TAB 3: COMBAT VISUALIZER (FLEET MODE) ===
    with tab_visualizer:
        col_t3_setup, col_t3_main = st.columns([1, 4], gap="large")
        
        with col_t3_setup:
            st.subheader("⚙️ Match Setup")
            t3_target = st.selectbox("Target Ship", defender_options, index=defender_options.index("Arrow") if "Arrow" in defender_options else 0, key="t3_tgt")
            
            t3_shield, t3_pp = render_target_components("t3", t3_target, db)
            t3_dist = st.number_input("Engagement Distance (m)", value=500.0, step=100.0, key="t3_dst")
            
            run_render = st.button("🎬 Generate Battle Render", type="primary", use_container_width=True)
            st.button("↺ Reset Target", key="rst_t3", use_container_width=True, on_click=reset_tab_defaults, args=("t3", "t3_tgt"))
            
            st.divider()
            
            # --- ATTACKER 1 (LEAD) ---
            st.markdown("### 🟢 Attacker 1 (Lead)")
            t3_attacker_1 = st.selectbox("Ship", attacker_options, index=attacker_options.index("F7A Hornet Mk II") if "F7A Hornet Mk II" in attacker_options else 0, key="t3_atk1")
            t3_trigger_1 = st.selectbox("Trigger Logic (A1)", ["Benchmark", "Human", "AI"], help=trigger_help, key="t3_trig1")
            t3_angle_1 = st.selectbox("Attack Angle (A1)", ["Front", "Right", "Rear", "Left"], key="t3_ang1")
            t3_force_1 = st.checkbox("Force Identical Weapons (A1)", value=True, key="t3_frc1")
            
            a1_ammo_mod = db.ship_configs[t3_attacker_1].get('max_ammo_mod', 1.0)
            a1_regen_mod = db.ship_configs[t3_attacker_1].get('max_regen_sec_mod', 1.0)
            attacker_hp_1 = db.ship_configs[t3_attacker_1]['hardpoints']
            selected_weapons_1 = []
            
            if t3_force_1:
                hp_counts_1 = collections.Counter(attacker_hp_1)
                for hp_size, count in sorted(hp_counts_1.items(), reverse=True):
                    valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                    default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                    w_choice = st.selectbox(f"{count}x Size {hp_size} Mounts", sorted(valid_w), index=default_idx, key=f"vis_hp1_grp_{hp_size}")
                    selected_weapons_1.extend([w_choice] * count) 
            else:
                for i, hp_size in enumerate(attacker_hp_1):
                    valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                    default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                    w_choice = st.selectbox(f"Slot {i+1} (S{hp_size})", sorted(valid_w), index=default_idx, key=f"vis_hp1_{i}")
                    selected_weapons_1.append(w_choice)

            st.divider()

            # --- ATTACKER 2 (WINGMAN) ---
            st.markdown("### 🔵 Attacker 2 (Wingman)")
            attacker_options_with_none = ["None"] + attacker_options
            t3_attacker_2 = st.selectbox("Ship", attacker_options_with_none, index=0, key="t3_atk2")
            
            selected_weapons_2 = []
            if t3_attacker_2 != "None":
                t3_trigger_2 = st.selectbox("Trigger Logic (A2)", ["Benchmark", "Human", "AI"], help=trigger_help, key="t3_trig2")
                t3_angle_2 = st.selectbox("Attack Angle (A2)", ["Front", "Right", "Rear", "Left"], index=1, key="t3_ang2")
                t3_force_2 = st.checkbox("Force Identical Weapons (A2)", value=True, key="t3_frc2")
                
                a2_ammo_mod = db.ship_configs[t3_attacker_2].get('max_ammo_mod', 1.0)
                a2_regen_mod = db.ship_configs[t3_attacker_2].get('max_regen_sec_mod', 1.0)
                attacker_hp_2 = db.ship_configs[t3_attacker_2]['hardpoints']
                if t3_force_2:
                    hp_counts_2 = collections.Counter(attacker_hp_2)
                    for hp_size, count in sorted(hp_counts_2.items(), reverse=True):
                        valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                        default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                        w_choice = st.selectbox(f"{count}x Size {hp_size} Mounts", sorted(valid_w), index=default_idx, key=f"vis_hp2_grp_{hp_size}")
                        selected_weapons_2.extend([w_choice] * count) 
                else:
                    for i, hp_size in enumerate(attacker_hp_2):
                        valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                        default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                        w_choice = st.selectbox(f"Slot {i+1} (S{hp_size})", sorted(valid_w), index=default_idx, key=f"vis_hp2_{i}")
                        selected_weapons_2.append(w_choice)
            else:
                t3_trigger_2 = "Benchmark"
                t3_angle_2 = 'Front'

        with col_t3_main:
            st.header("Interactive Combat Playback")
            if run_render:
                actual_pp = None if t3_pp == "Default" else t3_pp
                actual_shield = None if t3_shield == "None" else t3_shield
                
                vis_target = DefenderLoadout(t3_target, db, actual_pp)
                vis_target.equip_shields(actual_shield, db)
                shield_faces_val = getattr(vis_target, 'shield_faces', 1.0)
                
                vis_weapons_1 = [Weapon(db.weapons[w], a1_ammo_mod, a1_regen_mod) for w in selected_weapons_1]
                vis_weapons_2 = [Weapon(db.weapons[w], a2_ammo_mod, a2_regen_mod) for w in selected_weapons_2] if t3_attacker_2 != "None" else []
                
                with st.spinner("Rendering Physics..."):
                    frames, final_ttk, death_reason = simulate_visual_fight(
                        vis_weapons_1, vis_weapons_2, vis_target, 
                        engagement_distance=t3_dist, 
                        trigger_1=t3_trigger_1,
                        trigger_2=t3_trigger_2,
                        angle_1=t3_angle_1,
                        angle_2=t3_angle_2,
                        db=db
                    )
                    
                if len(frames) == 0:
                    st.error("Simulation failed to generate frames.")
                else:
                    st.success(f"Render Complete! TTK: {final_ttk:.2f}s ({death_reason})")
                    
                    json_frames = json.dumps(frames)
                    
                    canvas_w = 1100 if t3_attacker_2 != "None" else 900
                    
                    html_code = f"""
                    <div style="background-color: #1e1e24; padding: 15px; border-radius: 8px; font-family: monospace;">
                        <div style="margin-bottom: 15px; display: flex; align-items: center; gap: 15px;">
                            <button id="btnPlay" style="background: #0088ff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; flex-shrink: 0;">Play / Pause</button>
                            <button id="btnRestart" style="background: #444; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; flex-shrink: 0;">Restart</button>
                            <input type="range" id="timeSlider" min="0" max="{len(frames) - 1}" value="0" style="flex-grow: 1; cursor: pointer;">
                        </div>
                        <canvas id="simCanvas" width="{canvas_w}" height="550" style="display: block; margin: 0 auto; background-color: #0d0d12; border: 1px solid #333; border-radius: 4px;"></canvas>
                    </div>
                    
                    <script>
                        const frames = {json_frames};
                        const canvas = document.getElementById('simCanvas');
                        const ctx = canvas.getContext('2d');
                        const initialDistance = {t3_dist};
                        const slider = document.getElementById('timeSlider');
                        const shieldFaces = {int(shield_faces_val)};
                        
                        let currentFrame = 0;
                        let isPlaying = true;
                        let timer = null;
                        let flares = []; 
                        
                        function draw() {{
                            if(currentFrame >= frames.length) {{
                                isPlaying = false;
                                clearInterval(timer);
                                currentFrame = frames.length - 1; 
                            }}
                            
                            const frame = frames[currentFrame];
                            const cx = canvas.width / 2;
                            const targetY = 80;
                            
                            const hasAttacker2 = frame.w2 && frame.w2.length > 0;
                            const a1X = hasAttacker2 ? cx - 200 : cx;
                            const a1Y = canvas.height - 40;
                            const a2X = cx + 200;
                            const a2Y = canvas.height - 40;
                            
                            ctx.clearRect(0, 0, canvas.width, canvas.height);
                            
                            // --- UI BARS ---
                            ctx.fillStyle = '#aaaaaa';
                            ctx.font = '14px Arial';
                            ctx.fillText(`Time: ${{frame.t.toFixed(2)}}s`, 20, 30);
                            
                            const barWidth = 120;
                            const barX = canvas.width - 250;
                            let tY = 20;
    
                            // SHIELD BAR
                            const globalAvgS = (frame.s[0] + frame.s[1] + frame.s[2] + frame.s[3]) / 4.0;
                            
                            if (shieldFaces === 4) {{
                                ctx.fillStyle = '#cccccc'; 
                                ctx.fillText(`Shields (Quad): {{${{frame.tshp}}}}`, barX, tY);
                                tY += 5;
                                
                                const fNames = ['Front', 'Right', 'Rear', 'Left'];
                                for(let i=0; i<4; i++) {{
                                    tY += 18; 
                                    ctx.fillStyle = '#cccccc'; 
                                    ctx.font = '12px Arial';
                                    ctx.fillText(`${{fNames[i]}}:`, barX, tY);
                                    
                                    const quadBarWidth = 90; 
                                    const quadBarX = barX + 40; 
                                    
                                    // Health Bar
                                    ctx.fillStyle = '#333333'; ctx.fillRect(quadBarX, tY - 9, quadBarWidth, 8);
                                    ctx.fillStyle = '#00c8ff'; ctx.fillRect(quadBarX, tY - 9, quadBarWidth * frame.s[i], 8);
                                    
                                    if (frame.s[i] < 1.0 && frame.sr[i] < 1.0) {{
                                        ctx.fillStyle = '#555555'; ctx.fillRect(quadBarX, tY + 1, quadBarWidth, 3);
                                        ctx.fillStyle = '#00ffcc'; ctx.fillRect(quadBarX, tY + 1, quadBarWidth * frame.sr[i], 3);
                                    }}
                                    
                                    ctx.fillStyle = '#aaaaaa';
                                    ctx.fillText(`${{(frame.s[i]*100).toFixed(0)}}% {{${{frame.shp[i]}}}}`, quadBarX + quadBarWidth + 10, tY); 
                                }}
                                tY += 15;
                                ctx.font = '14px Arial'; 
                            }} else {{
                                ctx.fillStyle = '#cccccc'; 
                                ctx.fillText(`Shield: ${{(globalAvgS * 100).toFixed(1)}}% {{${{frame.tshp}}}}`, barX, tY);
                                ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
                                ctx.fillStyle = '#00c8ff'; ctx.fillRect(barX, tY + 5, barWidth * globalAvgS, 8);
                                
                                if (globalAvgS < 1.0 && frame.sr[0] < 1.0) {{
                                    ctx.fillStyle = '#555555'; ctx.fillRect(barX, tY + 14, barWidth, 3);
                                    ctx.fillStyle = '#00ffcc'; ctx.fillRect(barX, tY + 14, barWidth * frame.sr[0], 3);
                                }}
                                tY += 20;
                            }}
    
                            // ARMOR BAR WITH ABSOLUTE HP
                            tY += 30;
                            ctx.fillStyle = '#cccccc'; 
                            ctx.fillText(`Armor: ${{(frame.a * 100).toFixed(1)}}% `, barX, tY);
                            
                            let armorTextWidth = ctx.measureText(`Armor: ${{(frame.a * 100).toFixed(1)}}% `).width;
                            ctx.fillStyle = '#ffaa00'; 
                            ctx.fillText(`(${{frame.atp}}`, barX + armorTextWidth, tY);
                            let physWidth = ctx.measureText(`(${{frame.atp}}`).width;
                            
                            ctx.fillStyle = '#cccccc';
                            ctx.fillText(` / `, barX + armorTextWidth + physWidth, tY);
                            let sepWidth = ctx.measureText(` / `).width;
                            
                            ctx.fillStyle = '#00ffff';
                            ctx.fillText(`${{frame.ate}}) {{${{frame.ahp}}}}`, barX + armorTextWidth + physWidth + sepWidth, tY);

                            ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
                            ctx.fillStyle = '#ffaa00'; ctx.fillRect(barX, tY + 5, barWidth * frame.a, 8);

                            // HULL HP BAR WITH ABSOLUTE HP
                            tY += 30;
                            ctx.fillStyle = '#cccccc'; ctx.fillText(`Hull: ${{(frame.h * 100).toFixed(1)}}% {{${{frame.hhp}}}}`, barX, tY);
                            ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
                            ctx.fillStyle = '#aaaaaa'; ctx.fillRect(barX, tY + 5, barWidth * frame.h, 8);
    
                            // POWER PLANT BAR WITH ABSOLUTE HP
                            tY += 30;
                            ctx.fillStyle = '#cccccc'; ctx.fillText(`P.Plant: ${{(frame.pp * 100).toFixed(1)}}% {{${{frame.pphp}}}}`, barX, tY);
                            ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY + 5, barWidth, 8);
                            ctx.fillStyle = '#ff4444'; ctx.fillRect(barX, tY + 5, barWidth * frame.pp, 8);
                            
                            tY += 15;
                            ctx.fillStyle = '#333333'; ctx.fillRect(barX, tY, barWidth, 4);
                            ctx.fillStyle = '#bb00ff'; ctx.fillRect(barX, tY, barWidth * frame.pdh, 4);
                            
                            if (frame.pdh < 1.0 && frame.pdr < 1.0) {{
                                ctx.fillStyle = '#441166'; ctx.fillRect(barX, tY + 5, barWidth, 2);
                                ctx.fillStyle = '#eebbff'; ctx.fillRect(barX, tY + 5, barWidth * frame.pdr, 2);
                            }}

                            // --- TARGET SHIP ---
                            ctx.fillStyle = '#ff4444';
                            ctx.beginPath();
                            ctx.moveTo(cx, targetY + 25); 
                            ctx.lineTo(cx + 10, targetY + 5); 
                            ctx.lineTo(cx + 30, targetY - 15); 
                            ctx.lineTo(cx + 10, targetY - 10);
                            ctx.lineTo(cx, targetY - 5);       
                            ctx.lineTo(cx - 10, targetY - 10);
                            ctx.lineTo(cx - 30, targetY - 15); 
                            ctx.lineTo(cx - 10, targetY + 5);
                            ctx.fill();
                            
                            // --- SHIELDS ---
                            ctx.lineWidth = 6;
                            if (shieldFaces === 4) {{
                                const gap = 0.1;
                                // Top Arc (Ship's Rear - UI index 2)
                                ctx.strokeStyle = `rgba(0, 200, 255, ${{Math.max(0.1, frame.s[2])}})`;
                                ctx.beginPath(); ctx.arc(cx, targetY, 45, 5*Math.PI/4 + gap, 7*Math.PI/4 - gap); ctx.stroke();
                                
                                // Right Arc (Screen Right - UI index 1)
                                ctx.strokeStyle = `rgba(0, 200, 255, ${{Math.max(0.1, frame.s[1])}})`;
                                ctx.beginPath(); ctx.arc(cx, targetY, 45, 7*Math.PI/4 + gap, Math.PI/4 - gap + Math.PI*2); ctx.stroke();
                                
                                // Bottom Arc (Ship's Front / Nose - UI index 0)
                                ctx.strokeStyle = `rgba(0, 200, 255, ${{Math.max(0.1, frame.s[0])}})`;
                                ctx.beginPath(); ctx.arc(cx, targetY, 45, Math.PI/4 + gap, 3*Math.PI/4 - gap); ctx.stroke();
                                
                                // Left Arc (Screen Left - UI index 3)
                                ctx.strokeStyle = `rgba(0, 200, 255, ${{Math.max(0.1, frame.s[3])}})`;
                                ctx.beginPath(); ctx.arc(cx, targetY, 45, 3*Math.PI/4 + gap, 5*Math.PI/4 - gap); ctx.stroke();
                            }} else {{
                                if (globalAvgS > 0) {{
                                    ctx.strokeStyle = `rgba(0, 200, 255, ${{Math.max(0.1, globalAvgS)}})`;
                                    ctx.beginPath();
                                    ctx.arc(cx, targetY, 45, 0, Math.PI * 2);
                                    ctx.stroke();
                                }}
                            }}
                            
                            // --- ATTACKER 1 (GREEN) ---
                            ctx.fillStyle = '#44ff44';
                            ctx.beginPath();
                            ctx.moveTo(a1X, a1Y - 25); ctx.lineTo(a1X + 10, a1Y - 5); ctx.lineTo(a1X + 30, a1Y + 15); 
                            ctx.lineTo(a1X + 10, a1Y + 10); ctx.lineTo(a1X, a1Y + 5); ctx.lineTo(a1X - 10, a1Y + 10);
                            ctx.lineTo(a1X - 30, a1Y + 15); ctx.lineTo(a1X - 10, a1Y - 5); ctx.fill();

                            // --- ATTACKER 2 (BLUE) ---
                            if (hasAttacker2) {{
                                ctx.fillStyle = '#0088ff';
                                ctx.beginPath();
                                ctx.moveTo(a2X, a2Y - 25); ctx.lineTo(a2X + 10, a2Y - 5); ctx.lineTo(a2X + 30, a2Y + 15); 
                                ctx.lineTo(a2X + 10, a2Y + 10); ctx.lineTo(a2X, a2Y + 5); ctx.lineTo(a2X - 10, a2Y + 10);
                                ctx.lineTo(a2X - 30, a2Y + 15); ctx.lineTo(a2X - 10, a2Y - 5); ctx.fill();
                            }}

                            // --- FLARES ---
                            if (isPlaying && frame.i && frame.i.length > 0) {{
                                frame.i.forEach(imp => {{
                                    const x_off = imp[0];
                                    const p_type = imp[1];
                                    const owner = imp[2];
                                    
                                    let hitY = targetY + 15;
                                    if ((p_type === 1 || p_type === 2) && globalAvgS > 0) hitY = targetY + 45; 
                                    
                                    let hitX = cx + (x_off * 0.3);
                                    
                                    if (hasAttacker2) {{
                                        if (owner === 1) hitX -= 15; 
                                        if (owner === 2) hitX += 35; 
                                    }}
                                    
                                    flares.push({{ x: hitX, y: hitY, type: p_type, life: 1.0 }});
                                }});
                            }}

                            for (let i = flares.length - 1; i >= 0; i--) {{
                                let f = flares[i];
                                f.life -= 0.15; 
                                if (f.life <= 0) {{ flares.splice(i, 1); continue; }}
                                ctx.beginPath();
                                ctx.arc(f.x, f.y, (1 - f.life) * 15, 0, Math.PI * 2); 
                                let alpha = Math.max(0, f.life);
                                if (f.type === 2) ctx.fillStyle = `rgba(187, 0, 255, ${{alpha}})`; 
                                else if (f.type === 1) ctx.fillStyle = `rgba(0, 255, 255, ${{alpha}})`; 
                                else ctx.fillStyle = `rgba(255, 170, 0, ${{alpha}})`; 
                                ctx.fill();
                            }}
                            
                            // --- V-FORMATION PROJECTILES ---
                            frame.p.forEach(proj => {{
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
                                
                                if (hasAttacker2) {{
                                    if (owner === 1) targetDestX -= 15; 
                                    if (owner === 2) targetDestX += 35; 
                                }}
                                
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
                            }});
                            
                            // --- WEAPON HUD (ATTACKER 1) ---
                            let startX = 20;
                            let startY = canvas.height - (frame.w1.length * 25) - 10;
                            ctx.fillStyle = '#44ff44';
                            ctx.font = 'bold 12px Arial';
                            ctx.fillText(`🟢 A1 Weapons`, startX, startY - 15);
                            
                            frame.w1.forEach((wpn, idx) => {{
                                const isEnergy = wpn[0] === 1;
                                ctx.fillStyle = '#cccccc'; ctx.font = '11px Arial'; ctx.fillText(`S${{idx + 1}}`, startX, startY);
                                
                                if (isEnergy) {{
                                    const currentAmmo = wpn[1], maxAmmo = wpn[2], isRecharging = wpn[3];
                                    ctx.fillStyle = '#333333'; ctx.fillRect(startX + 25, startY - 8, 100, 8);
                                    ctx.fillStyle = isRecharging ? '#555555' : '#00ffff';
                                    ctx.fillRect(startX + 25, startY - 8, (currentAmmo / maxAmmo) * 100, 8);
                                    ctx.fillStyle = '#ffffff'; ctx.fillText(`${{currentAmmo.toFixed(0)}} / ${{maxAmmo}}`, startX + 135, startY);
                                }} else {{
                                    const totalAmmo = wpn[1], heatPct = wpn[2], ammoFired = wpn[3], isOverheated = wpn[4];
                                    ctx.fillStyle = '#333333'; ctx.fillRect(startX + 25, startY - 8, 100, 8);
                                    ctx.fillStyle = isOverheated ? '#ff0000' : '#ffaa00';
                                    ctx.fillRect(startX + 25, startY - 8, Math.min(heatPct, 100) || 0, 8);
                                    ctx.fillStyle = isOverheated ? '#ff0000' : '#ffffff';
                                    const heatStatus = isOverheated ? '🔥🔥🔥' : `🔥: ${{heatPct.toFixed(1)}}%`;
                                    ctx.fillText(`${{heatStatus}} | Ammo: ${{totalAmmo}}`, startX + 135, startY);
                                }}
                                startY += 25;
                            }});
                            
                            // --- WEAPON HUD (ATTACKER 2) ---
                            if (hasAttacker2) {{
                                let startX2 = canvas.width - 290;
                                let startY2 = canvas.height - (frame.w2.length * 25) - 10;
                                ctx.fillStyle = '#0088ff';
                                ctx.font = 'bold 12px Arial';
                                ctx.fillText(`🔵 A2 Weapons`, startX2, startY2 - 15);
                                
                                frame.w2.forEach((wpn, idx) => {{
                                    const isEnergy = wpn[0] === 1;
                                    ctx.fillStyle = '#cccccc'; ctx.font = '11px Arial'; ctx.fillText(`S${{idx + 1}}`, startX2, startY2);
                                    
                                    if (isEnergy) {{
                                        const currentAmmo = wpn[1], maxAmmo = wpn[2], isRecharging = wpn[3];
                                        ctx.fillStyle = '#333333'; ctx.fillRect(startX2 + 25, startY2 - 8, 100, 8);
                                        ctx.fillStyle = isRecharging ? '#555555' : '#00ffff';
                                        ctx.fillRect(startX2 + 25, startY2 - 8, (currentAmmo / maxAmmo) * 100, 8);
                                        ctx.fillStyle = '#ffffff'; ctx.fillText(`${{currentAmmo.toFixed(0)}} / ${{maxAmmo}}`, startX2 + 135, startY2);
                                    }} else {{
                                        const totalAmmo = wpn[1], heatPct = wpn[2], ammoFired = wpn[3], isOverheated = wpn[4];
                                        ctx.fillStyle = '#333333'; ctx.fillRect(startX2 + 25, startY2 - 8, 100, 8);
                                        ctx.fillStyle = isOverheated ? '#ff0000' : '#ffaa00';
                                        ctx.fillRect(startX2 + 25, startY2 - 8, Math.min(heatPct, 100) || 0, 8);
                                        ctx.fillStyle = isOverheated ? '#ff0000' : '#ffffff';
                                        const heatStatus = isOverheated ? '🔥🔥🔥' : `🔥: ${{heatPct.toFixed(1)}}%`;
                                        ctx.fillText(`${{heatStatus}} | Ammo: ${{totalAmmo}}`, startX2 + 135, startY2);
                                    }}
                                    startY2 += 25;
                                }});
                            }}
                            
                            if (frame.d) {{
                                ctx.fillStyle = '#ff0000';
                                ctx.font = 'bold 32px Arial';
                                ctx.textAlign = 'center';
                                ctx.fillText(`TARGET DESTROYED`, cx, canvas.height / 2);
                                ctx.textAlign = 'left'; 
                            }}
                            
                            if (isPlaying) {{
                                slider.value = currentFrame;
                                currentFrame++;
                            }}
                        }}
                        
                        slider.addEventListener('input', (e) => {{
                            currentFrame = parseInt(e.target.value);
                            isPlaying = false; 
                            flares = []; 
                            clearInterval(timer);
                            draw(); 
                        }});
                        
                        document.getElementById('btnPlay').onclick = () => {{
                            if (currentFrame >= frames.length - 1) {{
                                currentFrame = 0; 
                                flares = [];
                            }}
                            isPlaying = !isPlaying;
                            if(isPlaying) timer = setInterval(draw, 50); 
                            else clearInterval(timer);
                        }};
                        
                        document.getElementById('btnRestart').onclick = () => {{
                            currentFrame = 0;
                            slider.value = 0;
                            isPlaying = true;
                            flares = [];
                            clearInterval(timer);
                            timer = setInterval(draw, 50);
                        }};
                        
                        timer = setInterval(draw, 50);
                    </script>
                    """
                    components.html(html_code, height=600)
            else:
                st.info("Configure your matchup on the left and click 'Generate Battle Render' to begin.")