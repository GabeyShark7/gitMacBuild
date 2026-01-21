# =========================
# voice_operations.py
# Fast, accurate, auto-adjusting voice dictation for SharkPad
# =========================

import os
import sys
import platform
import warnings
import numpy as np
from PySide6.QtCore import QThread, Signal

warnings.filterwarnings("ignore")

# -----------------------------
# Suppress ALSA/JACK errors
# -----------------------------
os.environ["ALSA_CARD"] = "default"
_stderr_backup = sys.stderr
sys.stderr = open(os.devnull, "w")

try:
    import speech_recognition as sr
except ImportError:
    sr = None
finally:
    sys.stderr.close()
    sys.stderr = _stderr_backup

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("ERROR: faster-whisper not installed. Run: pip install faster-whisper")

# -----------------------------
# Voice Worker Thread
# -----------------------------
class VoiceWorker(QThread):
    text_received = Signal(str)
    error_occurred = Signal(str)
    audio_level = Signal(int)  # 0-100

    def __init__(self):
        super().__init__()
        self.energy_threshold = 600  # Default sensitivity
        self.running = True

    def set_sensitivity(self, value):
        """Adjust microphone sensitivity (100-4000)"""
        self.energy_threshold = value

    def run(self):
        if not WHISPER_AVAILABLE or sr is None:
            self.error_occurred.emit("Whisper or SpeechRecognition not installed")
            return

        _stderr_orig = sys.stderr
        try:
            sys.stderr = sys.__stderr__
            print("\n=== Loading Whisper Model ===")
            model_device = "cpu"
            model_compute = "float32" if platform.system() == "Darwin" else "int8"
            model = WhisperModel("base", device=model_device, compute_type=model_compute)
            print("Whisper model loaded successfully!\n")
            sys.stderr = open(os.devnull, "w")

            r = sr.Recognizer()
            r.energy_threshold = self.energy_threshold
            r.dynamic_energy_threshold = True
            r.pause_threshold = 0.6
            r.phrase_threshold = 0.3
            r.non_speaking_duration = 0.3

            mic = sr.Microphone(sample_rate=16000)
            with mic as source:
                r.adjust_for_ambient_noise(source, duration=1)
                print("Ready! Start speaking...")

                while self.running:
                    try:
                        # -------- Audio level meter (fixed) --------
                        try:
                            audio_data = source.stream.read(1024)
                        except TypeError:
                            # Fallback if exception_on_overflow not supported
                            audio_data = source.stream.read(1024)
                        
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)

                        if audio_array.size == 0:
                            rms = 0.0
                        else:
                            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2))

                        # Scale RMS relative to sensitivity for proper bar
                        level = min(100, max(0, int((rms / max(50, self.energy_threshold)) * 100)))
                        self.audio_level.emit(level)

                        # Listen for speech
                        audio = r.listen(source, timeout=0.3, phrase_time_limit=15)

                        # Convert to float32 numpy for faster-whisper
                        raw = audio.get_raw_data()
                        audio_float = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

                        # Transcribe
                        segments, _ = model.transcribe(
                            audio_float,
                            beam_size=5,
                            language="en",
                            condition_on_previous_text=False,
                            vad_filter=True,
                            vad_parameters=dict(
                                threshold=0.5,
                                min_speech_duration_ms=200,
                                min_silence_duration_ms=400
                            )
                        )

                        # Collect text
                        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
                        if text:
                            self.text_received.emit(text)

                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        sys.stderr = _stderr_orig
                        print(f"Recognition error: {e}")
                        sys.stderr = open(os.devnull, "w")
        except Exception as e:
            sys.stderr = _stderr_orig
            self.error_occurred.emit(str(e))
            import traceback
            traceback.print_exc()
        finally:
            if sys.stderr != _stderr_orig:
                try:
                    sys.stderr.close()
                except:
                    pass
            sys.stderr = _stderr_orig

    def stop(self):
        self.running = False
        self.quit()  # Tell the thread to quit its event loop
        self.wait()  # Wait for it to finish

# -----------------------------
# Global Voice Worker Reference
# -----------------------------
_voice_worker_ref = None

def toggle_voice(editor, level_callback=None, sensitivity=600):
    global _voice_worker_ref
    if _voice_worker_ref and _voice_worker_ref.isRunning():
        _voice_worker_ref.stop()
        _voice_worker_ref.wait(3000)  # Wait up to 3 seconds
        if _voice_worker_ref.isRunning():
            _voice_worker_ref.terminate()  # Force terminate if still running
            _voice_worker_ref.wait(1000)
        _voice_worker_ref.deleteLater()  # Schedule for deletion
        _voice_worker_ref = None
        print("Voice recognition stopped.")
        return False

    _voice_worker_ref = VoiceWorker()
    _voice_worker_ref.set_sensitivity(sensitivity)
    _voice_worker_ref.text_received.connect(lambda t: editor.insertPlainText(t + " "))
    _voice_worker_ref.error_occurred.connect(lambda e: print(f"Voice error: {e}"))
    if level_callback:
        _voice_worker_ref.audio_level.connect(level_callback)
    _voice_worker_ref.start()
    return True

def set_sensitivity(value):
    global _voice_worker_ref
    if _voice_worker_ref and _voice_worker_ref.isRunning():
        _voice_worker_ref.set_sensitivity(value)

def is_voice_active():
    global _voice_worker_ref
    return _voice_worker_ref is not None and _voice_worker_ref.isRunning()

def stop_voice():
    global _voice_worker_ref
    if _voice_worker_ref and _voice_worker_ref.isRunning():
        _voice_worker_ref.stop()
        _voice_worker_ref.wait(3000)
        if _voice_worker_ref.isRunning():
            _voice_worker_ref.terminate()
            _voice_worker_ref.wait(1000)
        _voice_worker_ref.deleteLater()
        _voice_worker_ref = None