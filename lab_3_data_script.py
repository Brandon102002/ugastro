import threading
import time
import json
import ugradio
from interf import Interferometer
from snap import UGRadioSnap
from sdr import SDR, capture_data
from coord import get_altaz, sunpos
import numpy as np

print("Local Time:", ugradio.timing.local_time())
print("UTC Time:", ugradio.timing.utc())
print("Unix Time:", ugradio.timing.unix_time())
print("Julian Date:", ugradio.timing.julian_date())
print("Local Sidereal Time (LST):", ugradio.timing.lst())

# Initialize components
interf = Interferometer()
snap = UGRadioSnap()
DATA_FILE = "observations.json"
data_lock = threading.Lock()
collected_data = []
terminate_flag = threading.Event()

# ======= TELESCOPE POINTING ======= #
def point_telescope(target_alt, target_az):
    """Continuously adjust telescope pointing."""
    try:
        while not terminate_flag.is_set():
            interf.point(target_alt, target_az)
            print(f"Telescope pointed to Alt: {target_alt}, Az: {target_az}")
            time.sleep(5)
    except Exception as e:
        print(f"Telescope error: {e}")

# ======= DATA COLLECTION ======= #
def collect_spectrometer_data(duration):
    """Collect data from SNAP spectrometer."""
    prev_cnt = None
    start_time = time.time()
    try:
        while time.time() - start_time < duration and not terminate_flag.is_set():
            data = snap.read_data(prev_cnt)
            if "acc_cnt" in data:
                prev_cnt = data["acc_cnt"]
                with data_lock:
                    collected_data.append({"time": ugradio.timing.utc(), "spectra": data})
            time.sleep(1)
        print("Spectrometer finished collecting.")
    except Exception as e:
        print(f"Spectrometer error: {e}")

def collect_sdr_data(nsamples, nblocks, duration):
    """Collect data from SDR dongle."""
    try:
        sdr = SDR()
        start_time = time.time()
        while time.time() - start_time < duration and not terminate_flag.is_set():
            sdr_data = sdr.capture_data(nsamples=nsamples, nblocks=nblocks)
            with data_lock:
                collected_data.append({"time": ugradio.timing.utc(), "sdr": sdr_data})
            time.sleep(1)
        print("SDR finished collecting.")
    except Exception as e:
        print(f"SDR error: {e}")

# ======= DATA SAVING ======= #
def save_data_periodically():
    """Periodically save collected data to file."""
    try:
        while not terminate_flag.is_set():
            with data_lock:
                with open(DATA_FILE, "w") as f:
                    json.dump(collected_data, f, indent=4)
            print("Data saved successfully.")
            time.sleep(10)
    except Exception as e:
        print(f"Error saving data: {e}")

# ======= USER INPUT ======= #
try:
    observe_sun = input("Observe the Sun? (yes/no): ").strip().lower() == "yes"
    process_coords = not observe_sun and input("Process RA/Dec coordinates? (yes/no): ").strip().lower() == "yes"

    if observe_sun:
        jd = ugradio.timing.julian_date()
        ra, dec = sunpos(jd)
        lat, lon, alt = 37.8716, -122.2727, 0  # Example location (Berkeley, CA)
        target_alt, target_az = get_altaz(ra, dec, jd, lat, lon, alt)
        print(f"Sun Position -> Alt: {target_alt:.2f}, Az: {target_az:.2f}")

    elif process_coords:
        ra = float(input("Enter RA (degrees): "))
        dec = float(input("Enter Dec (degrees): "))
        jd = time.time() / 86400.0 + 2440587.5
        lat, lon, alt = 37.8716, -122.2727, 0
        target_alt, target_az = get_altaz(ra, dec, jd, lat, lon, alt)

    else:
        target_alt = float(input("Enter Altitude (degrees): "))
        target_az = float(input("Enter Azimuth (degrees): "))

    nsamples = int(input("Enter samples per block: "))
    nblocks = int(input("Enter number of blocks: "))
    duration = float(input("Enter total duration (seconds): "))

except Exception as e:
    print(f"Input error: {e}")
    exit()

# ======= START THREADS ======= #
telescope_thread = threading.Thread(target=point_telescope, args=(target_alt, target_az))
spectrometer_thread = threading.Thread(target=collect_spectrometer_data, args=(duration,))
sdr_thread = threading.Thread(target=collect_sdr_data, args=(nsamples, nblocks, duration))
save_thread = threading.Thread(target=save_data_periodically)

for t in [telescope_thread, spectrometer_thread, sdr_thread, save_thread]:
    t.daemon = True
    t.start()

# ======= MAIN EXECUTION ======= #
try:
    start_time = time.time()
    while time.time() - start_time < duration:
        time.sleep(1)
    print("Time duration reached, waiting for last block to complete...")
    terminate_flag.set()
except KeyboardInterrupt:
    print("\nTerminating data collection...")
    terminate_flag.set()
except Exception as e:
    print(f"Unexpected error: {e}")
    terminate_flag.set()

print("Data collection completed.")