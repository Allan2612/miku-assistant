import comtypes
comtypes.CoInitialize()
from pycaw.pycaw import AudioUtilities
from pycaw.constants import AudioDeviceState

endpoints = []
try:
    endpoints.append(AudioUtilities.GetSpeakers().EndpointVolume)
except Exception:
    pass

for d in AudioUtilities.GetAllDevices():
    if d.state == AudioDeviceState.Active and getattr(d, 'id', '').startswith('{0.0.0.'):
        try:
            ep = d.EndpointVolume
            if ep not in endpoints:
                endpoints.append(ep)
                print(f"Found active output device: {d.FriendlyName}")
        except Exception:
            pass

print(f"Total active output endpoints to control: {len(endpoints)}")
for ep in endpoints:
    vol = ep.GetMasterVolumeLevelScalar()
    print(f"  Current: {round(vol*100)}%")
