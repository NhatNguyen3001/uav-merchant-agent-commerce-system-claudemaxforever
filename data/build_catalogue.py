"""Writes data/catalogue.json. Run: python data/build_catalogue.py"""
import json
from pathlib import Path

CERT = {"materials": ["recycled ABS", "aluminium"], "certifications": ["B Corp", "FSC packaging"], "brand_practice": "carbon neutral shipping"}
PART = {"materials": ["aluminium", "steel"], "certifications": [], "brand_practice": "repair program"}
NONE = {"materials": ["plastic"], "certifications": [], "brand_practice": ""}

# sku, name, type, list, cost, stock, ship, suited_for, sustainability, durability, compat, outcomes
ROWS = [
    ("MIC-DYN-01", "Northwind D1 dynamic microphone", "microphone", 179, 110, 12, 2, ["beginner", "noisy_room", "small_space"], CERT, "high", ["usb_interface", "xlr"], ["podcast", "voice", "rejects_background_noise"]),
    ("MIC-DYN-02", "Northwind D2 broadcast dynamic", "microphone", 329, 210, 5, 3, ["intermediate", "noisy_room"], CERT, "high", ["xlr"], ["podcast", "broadcast", "rejects_background_noise"]),
    ("MIC-CON-01", "Clearline C1 large diaphragm condenser", "microphone", 249, 150, 8, 2, ["intermediate", "treated_room"], PART, "medium", ["xlr"], ["vocals", "studio", "detailed"]),
    ("MIC-CON-02", "Clearline C2 pencil condenser pair", "microphone", 299, 180, 4, 4, ["advanced", "treated_room"], PART, "medium", ["xlr"], ["instruments", "stereo"]),
    ("MIC-USB-01", "Plugtalk U1 USB microphone", "microphone", 99, 60, 20, 1, ["beginner", "small_space"], NONE, "medium", ["usb"], ["podcast", "calls", "plug_and_play"]),
    ("MIC-USB-02", "Plugtalk U2 USB microphone with mute", "microphone", 129, 80, 15, 1, ["beginner", "small_space"], NONE, "medium", ["usb"], ["podcast", "streaming", "plug_and_play"]),
    ("MIC-LAV-01", "Whisper L1 lavalier", "microphone", 59, 30, 30, 1, ["beginner", "mobile"], NONE, "low", ["3.5mm", "usb_c"], ["interviews", "mobile"]),
    ("IF-USB-01", "Loopline U1 USB audio interface", "audio_interface", 144, 95, 9, 2, ["beginner"], CERT, "high", ["xlr", "usb"], ["podcast", "plug_and_play", "previous_generation"]),
    ("IF-USB-02", "Loopline U2 USB audio interface", "audio_interface", 199, 130, 10, 2, ["beginner", "small_space"], CERT, "high", ["xlr", "usb_c"], ["podcast", "plug_and_play", "one_knob_gain"]),
    ("IF-USB-03", "Loopline U4 four channel interface", "audio_interface", 349, 230, 6, 3, ["intermediate"], CERT, "high", ["xlr", "usb_c"], ["multi_guest", "podcast"]),
    ("IF-USB-04", "Gridwave G2 interface", "audio_interface", 229, 150, 7, 2, ["intermediate"], PART, "medium", ["xlr", "usb_c"], ["music", "podcast"]),
    ("IF-MIX-01", "Gridwave M6 podcast mixer", "audio_interface", 449, 300, 3, 5, ["advanced"], PART, "high", ["xlr", "usb_c"], ["multi_guest", "live_show"]),
    ("HP-REC-01", "Evergreen R1 recycled shell headphones", "headphones", 149, 90, 14, 1, ["beginner", "small_space"], CERT, "high", ["3.5mm", "6.35mm"], ["monitoring", "closed_back", "isolation"]),
    ("HP-REC-02", "Evergreen R2 recycled shell headphones", "headphones", 199, 120, 8, 2, ["intermediate"], CERT, "high", ["3.5mm", "6.35mm"], ["monitoring", "closed_back"]),
    ("HP-STD-01", "Baseline S1 closed back headphones", "headphones", 89, 50, 25, 1, ["beginner"], NONE, "medium", ["3.5mm"], ["monitoring", "closed_back"]),
    ("HP-STD-02", "Baseline S2 open back headphones", "headphones", 159, 95, 6, 2, ["intermediate", "treated_room"], NONE, "medium", ["3.5mm", "6.35mm"], ["mixing", "open_back"]),
    ("HP-PRO-01", "Reference P1 studio headphones", "headphones", 299, 190, 4, 3, ["advanced"], PART, "high", ["6.35mm"], ["mixing", "mastering"]),
    ("ARM-DESK-01", "Compact desk clamp boom arm", "boom_arm", 165, 100, 11, 1, ["small_space", "beginner"], CERT, "high", ["standard_thread"], ["desk_mount", "small_space", "low_profile"]),
    ("ARM-DESK-02", "Standard desk boom arm", "boom_arm", 79, 45, 18, 1, ["beginner"], NONE, "medium", ["standard_thread"], ["desk_mount"]),
    ("ARM-PRO-01", "Broadcast boom arm with cable channel", "boom_arm", 219, 140, 5, 3, ["advanced"], PART, "high", ["standard_thread"], ["desk_mount", "broadcast"]),
    ("STD-TAB-01", "Tabletop tripod stand", "boom_arm", 29, 15, 40, 1, ["beginner", "mobile"], NONE, "low", ["standard_thread"], ["tabletop", "mobile"]),
    ("POP-01", "Mesh pop filter", "pop_filter", 25, 10, 50, 1, ["beginner"], NONE, "medium", ["gooseneck_clamp"], ["plosives"]),
    ("POP-02", "Metal pop filter", "pop_filter", 39, 18, 30, 1, ["intermediate"], PART, "high", ["gooseneck_clamp"], ["plosives"]),
    ("POP-03", "Foam windscreen for dynamic mics", "pop_filter", 15, 6, 60, 1, ["beginner", "mobile"], NONE, "low", ["MIC-DYN-01", "MIC-DYN-02"], ["plosives", "wind"]),
    ("PAN-01", "Acoustic panel 4 pack recycled PET", "acoustic_panel", 129, 70, 10, 4, ["small_space", "noisy_room"], CERT, "medium", [], ["reflection_control", "small_space"]),
    ("PAN-02", "Acoustic panel 8 pack recycled PET", "acoustic_panel", 229, 130, 6, 4, ["treated_room"], CERT, "medium", [], ["reflection_control"]),
    ("PAN-03", "Reflection filter shield", "acoustic_panel", 149, 85, 7, 3, ["small_space", "noisy_room"], PART, "high", ["standard_thread"], ["reflection_control", "isolation"]),
    ("PAN-04", "Door seal kit", "acoustic_panel", 49, 20, 20, 2, ["noisy_room"], NONE, "medium", [], ["noise_reduction"]),
    ("CAB-XLR-01", "XLR cable 3m recycled jacket", "cable", 24, 9, 80, 1, ["beginner"], CERT, "high", ["xlr"], ["connectivity"]),
    ("CAB-USB-01", "USB-C cable 2m", "cable", 19, 7, 100, 1, ["beginner"], NONE, "medium", ["usb_c"], ["connectivity"]),
    ("BUN-STA-01", "Starter podcast kit (USB mic, stand, pop filter)", "kit", 149, 95, 6, 2, ["beginner", "small_space"], NONE, "medium", ["usb"], ["podcast", "plug_and_play"]),
    ("MON-01", "Compact studio monitors pair", "monitors", 279, 180, 4, 5, ["intermediate", "treated_room"], PART, "high", ["6.35mm", "rca"], ["mixing"]),
]


def build():
    out = []
    for sku, name, typ, lp, cost, stock, ship, suited, sus, dur, compat, outcomes in ROWS:
        out.append({
            "sku": sku, "name": name, "type": typ, "list_price": lp, "cost": cost,
            "stock": stock, "ship_days": ship, "specs": {"weight_g": 400 if typ == "microphone" else 300},
            "suited_for": suited, "sustainability": sus, "durability": dur,
            "compatibility": compat, "outcome_tags": outcomes,
        })
    Path(__file__).with_name("catalogue.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {len(out)} products")


if __name__ == "__main__":
    build()
