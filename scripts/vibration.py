import iio
import numpy as np
import sys

# 1. Setup Context and Device
ctx = iio.Context("ip:192.168.1.34")
ctx.set_timeout(0)
dev = ctx.find_device("cf_axi_adc")

if dev is None:
    print("Error: cf_axi_adc not found")
    sys.exit(1)

# 2. Dynamically find, enable, and get the scale for all 8 channels
channels = []
scales = []
num_channels = 8

print("Initializing channels...")
for i in range(num_channels):
    ch_name = f"voltage{i}"
    ch = dev.find_channel(ch_name)
    if ch:
        ch.enabled = True
        channels.append(ch)
        scales.append(float(ch.attrs["scale"].value))
    else:
        print(f"Error: Could not find {ch_name}")
        sys.exit(1)

# 3. Create Buffer (4096 samples per channel)
buf = iio.Buffer(dev, 4096)

print(f"\nStarting continuous read for {len(channels)} channels... Press Ctrl+C to stop.\n")

try:
    while True:
        buf.refill()

        raw_data = np.frombuffer(buf.read(), dtype=np.int32)
        if raw_data.size < len(channels):
            continue

        interleaved_data = raw_data.reshape(-1, len(channels))

        # Shift out 8-bit status header, keep signed 24-bit ADC data
        shifted_up = np.left_shift(interleaved_data, 8)
        true_24bit_data = np.right_shift(shifted_up, 8)

        output_strings = []

        for i in range(len(channels)):
            # Latest raw ADC count for this channel (no RMS / peak)
            raw_value = int(true_24bit_data[-1, i])
            output_strings.append(f"C{i} Raw:{raw_value}")

        final_output = " | ".join(output_strings)
        print(f"\r{final_output}    ", end="", flush=True)

except KeyboardInterrupt:
    print("\n\nData acquisition gracefully stopped.")
except OSError as e:
    print(f"\n\nConnection error: {e}")
    print("Check ZedBoard power, cable, IP 192.168.1.34, and iiod on the board.")
    sys.exit(1)
