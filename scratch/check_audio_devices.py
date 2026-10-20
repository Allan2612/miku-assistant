import comtypes
comtypes.CoInitialize()
from pycaw.pycaw import AudioUtilities
from pycaw.constants import AudioDeviceState

devices = AudioUtilities.GetAllDevices()
print(f"Total audio devices: {len(devices)}")
for d in devices:
    if d.state == AudioDeviceState.Active:
        try:
            vol_endpoint = d.EndpointVolume
            vol = vol_endpoint.GetMasterVolumeLevelScalar()
            mute = vol_endpoint.GetMute()
            print(f"ACTIVE: '{d.FriendlyName}' | Vol: {round(vol*100)}% | Mute: {mute} | ID: {d.id}")
        except Exception as e:
            # Some devices may be microphone / input endpoints
            print(f"ACTIVE (input/other): '{d.FriendlyName}' | Error: {e}")
