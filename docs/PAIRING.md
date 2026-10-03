# Pairing

Pairing connects your laptop to your Muse. It uses Bluetooth LE and takes
about a minute. You do it once; the service reconnects on its own after
that, across reboots.

## What you need

- A laptop running Omarchy 4 with musarchy installed (see the README).
- An SDK token from [gadgets.muse.ai](https://gadgets.muse.ai)
  (Account > SDK tokens). Every gadget needs one. Read the Gadget SDK
  Terms there before you use it.
- The Muse app on your phone, on the same network as the laptop.

## Steps

1. Install with your token:

   ```bash
   bash install.sh --sdk-token mgst_...
   ```

   The installer prints the Bluetooth device name when it opens pairing.
   It looks like `MuseGadgetXXXXXX`.

2. In the Muse app, turn on **Settings > Devices > Developer mode**.

3. Add a device (**Settings > Devices > Add Device**, the **+** icon).
   Choose the name the installer printed.

4. The app warns that this is a community device. Continue if it is yours.

5. When asked for Wi-Fi, pick the network shown. The laptop is already
   online, so no password is needed.

Done. The device connects to your Muse and stays connected.

## Notes

- Pairing stays open for 10 minutes. To open it again later, run
  `sudo musegadget pair`.
- To pair a second phone or start over, run `sudo musegadget pair --force`.
- Bluetooth LE is required. If the installer warned about a missing
  adapter, pairing cannot work until one is present.
- iPhones are picky about Bluetooth state. If the phone shows a generic
  connection error, toggle the phone's Bluetooth off and on and try again.
