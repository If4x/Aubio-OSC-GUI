import threading
import time
import aubio
import numpy as np
import pyaudio
import customtkinter as ctk
from pythonosc import udp_client

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def trigger_beat_pulse(client):
    """Sends a non-blocking press (255) and release (0) pulse to QLC+."""
    client.send_message("/qlc/beat", 255)
    time.sleep(0.03)
    client.send_message("/qlc/beat", 0)


class AubioBpmApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Aubio Live BPM Engine -> QLC+")
        self.geometry("420x520")
        self.resizable(False, False)

        self.is_running = False
        self.audio = pyaudio.PyAudio()

        # OSC Client - using local port 7770
        self.osc_client = udp_client.SimpleUDPClient("127.0.0.1", 7770)

        # UI Elements
        ctk.CTkLabel(self, text="Aubio Beat Detector", font=("Arial", 22, "bold")).pack(pady=(15, 5))

        # Audio Input Dropdown
        ctk.CTkLabel(self, text="Select Virtual Audio Input:").pack(anchor="w", padx=30)
        self.devices = self.get_audio_devices()
        self.device_var = ctk.StringVar(value=list(self.devices.keys())[0] if self.devices else "No Device")
        self.device_dropdown = ctk.CTkOptionMenu(self, values=list(self.devices.keys()), variable=self.device_var)
        self.device_dropdown.pack(fill="x", padx=30, pady=(0, 15))

        # Sensitivity / Threshold Slider
        ctk.CTkLabel(self, text="Silence Threshold (dB):").pack(anchor="w", padx=30)
        self.silence_slider = ctk.CTkSlider(self, from_=-90, to=0, number_of_steps=90)
        self.silence_slider.set(-40)
        self.silence_slider.pack(fill="x", padx=30, pady=(0, 10))

        # Visual Beat Pulse Indicator
        self.pulse_frame = ctk.CTkFrame(self, width=30, height=30, corner_radius=15, fg_color="#333333")
        self.pulse_frame.pack(pady=(10, 5))

        # BPM & Millisecond Display
        self.bpm_label = ctk.CTkLabel(self, text="-- BPM (-- ms)", font=("Arial", 30, "bold"), text_color="#1f538d")
        self.bpm_label.pack(pady=10)

        # Control Buttons
        self.start_btn = ctk.CTkButton(self, text="Start Tracking", command=self.toggle_tracking, fg_color="#2fa572", hover_color="#1e7e54")
        self.start_btn.pack(pady=10)

        # Test Button
        self.test_btn = ctk.CTkButton(self, text="Send Test OSC Pulse", command=self.send_test_pulse, fg_color="#e67e22", hover_color="#d35400")
        self.test_btn.pack(pady=5)

    def trigger_pulse_animation(self):
        """Flashes the indicator circle neon green and resets after 100ms."""
        self.pulse_frame.configure(fg_color="#00FF66")
        self.after(100, lambda: self.pulse_frame.configure(fg_color="#333333"))

    def send_test_pulse(self):
        """Manually triggers an OSC beat pulse to test connection."""
        threading.Thread(target=trigger_beat_pulse, args=(self.osc_client,), daemon=True).start()
        self.trigger_pulse_animation()

    def get_audio_devices(self):
        devs = {}
        for i in range(self.audio.get_device_count()):
            dev_info = self.audio.get_device_info_by_index(i)
            if dev_info.get("maxInputChannels") > 0:
                devs[f"{i}: {dev_info.get('name')}"] = i
        return devs

    def update_ui_on_beat(self, bpm, ms):
        """Thread-safe method to update label text and trigger pulse animation."""
        self.bpm_label.configure(text=f"{bpm:.1f} BPM ({int(ms)} ms)")
        self.trigger_pulse_animation()

    def toggle_tracking(self):
        if not self.is_running:
            self.is_running = True
            self.start_btn.configure(text="Stop Tracking", fg_color="#c0392b", hover_color="#962d22")
            self.device_dropdown.configure(state="disabled")
            threading.Thread(target=self.process_audio, daemon=True).start()
        else:
            self.is_running = False
            self.start_btn.configure(text="Start Tracking", fg_color="#2fa572", hover_color="#1e7e54")
            self.device_dropdown.configure(state="normal")
            self.bpm_label.configure(text="-- BPM (-- ms)")
            self.pulse_frame.configure(fg_color="#333333")

    def process_audio(self):
        buf_size = 1024
        hop_size = 512
        sample_rate = 44100
        dev_idx = self.devices[self.device_var.get()]

        tempo = aubio.tempo("default", buf_size, hop_size, sample_rate)

        try:
            stream = self.audio.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=dev_idx,
                frames_per_buffer=hop_size
            )
        except Exception as e:
            print(f"Error opening audio stream: {e}")
            self.is_running = False
            return

        while self.is_running:
            tempo.set_silence(self.silence_slider.get())
            try:
                data = stream.read(hop_size, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.float32)

                if tempo(samples):
                    bpm = tempo.get_bpm()
                    if bpm > 0:
                        ms = 60000.0 / bpm

                        # 1. Send OSC pulse to QLC+
                        threading.Thread(target=trigger_beat_pulse, args=(self.osc_client,), daemon=True).start()

                        # 2. Update UI safely from main GUI loop via self.after
                        self.after(0, self.update_ui_on_beat, bpm, ms)
            except Exception:
                break

        stream.stop_stream()
        stream.close()


if __name__ == "__main__":
    app = AubioBpmApp()
    app.mainloop()