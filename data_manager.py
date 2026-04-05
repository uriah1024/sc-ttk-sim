import os
import csv
import re

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