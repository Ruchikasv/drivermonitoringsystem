/**
 * Synthesized Web Audio Alert Manager for Intelligent Driver Monitoring.
 *
 * Implements:
 * - Level 1: Short, pleasant warning chime (880Hz, 160ms, debounced 3.5s) - One-shot
 * - Level 2: Escalation pulse (dual-tone 620Hz -> 880Hz, 360ms, debounced 2.5s) - One-shot
 * - Level 3: Critical emergency continuous warble siren (urgent 960Hz / 480Hz sweep)
 *            Runs continuously via a hardware-modulated LFO oscillator while driver remains in Level 3 Critical state.
 *            Stops immediately when alert tier is no longer Critical (e.g. Warning, Nudge, Safe, Paused, or Ended).
 * - Singleton AudioContext with active state resumption and diagnostic logging.
 */

export class SoundManager {
  constructor() {
    this.audioCtx = null;
    this.enabled = true;
    this.lastPlayedTier = null;
    this.lastPlayTime = 0;

    // Single-shot oscillator references
    this.currentOscillator = null;
    this.currentGain = null;

    // Continuous Level 3 siren hardware nodes
    this.isCriticalPlaying = false;
    this.criticalCarrierOsc = null;
    this.criticalLfoOsc = null;
    this.criticalLfoGain = null;
    this.criticalMainGain = null;

    this.cooldowns = {
      nudge: 3500,    // Level 1: 3.5s cooldown (one-shot)
      warning: 2500,  // Level 2: 2.5s cooldown (one-shot)
      critical: 1500, // Level 3: continuous siren
    };
  }

  /**
   * Ensure AudioContext is created and running.
   */
  _getAudioContext() {
    if (typeof window === 'undefined') return null;
    try {
      if (!this.audioCtx) {
        const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
        if (AudioCtxClass) {
          this.audioCtx = new AudioCtxClass();
          console.log(`[SoundManager] AudioContext created. State: ${this.audioCtx.state}`);
        }
      }
      if (this.audioCtx) {
        console.log(`[SoundManager] AudioContext state: ${this.audioCtx.state}`);
        if (this.audioCtx.state === 'suspended') {
          this.audioCtx.resume().then(() => {
            console.log(`[SoundManager] AudioContext resumed successfully. State: ${this.audioCtx.state}`);
          }).catch((err) => {
            console.warn('[SoundManager] AudioContext resume failed:', err);
          });
        }
      }
      return this.audioCtx;
    } catch (err) {
      console.warn('[SoundManager] Could not initialize AudioContext:', err);
      return null;
    }
  }

  /**
   * Unlock AudioContext on initial user gesture / shift start / button interaction.
   */
  unlockAudio() {
    const ctx = this._getAudioContext();
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().then(() => {
        console.log(`[SoundManager] Audio unlocked on user gesture. State: ${ctx.state}`);
      }).catch((err) => {
        console.warn('[SoundManager] Audio unlock error:', err);
      });
    }
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    if (!enabled) {
      this.stop();
    }
  }

  /**
   * Stop any active audio output and cancel critical siren.
   */
  stop() {
    this.stopCriticalSiren();
    if (this.currentOscillator) {
      try {
        this.currentOscillator.stop();
        this.currentOscillator.disconnect();
      } catch {}
      this.currentOscillator = null;
    }
    if (this.currentGain) {
      try {
        this.currentGain.disconnect();
      } catch {}
      this.currentGain = null;
    }
  }

  /**
   * Starts the continuous Level 3 Critical emergency siren.
   * Uses a hardware LFO-modulated oscillator for seamless, continuous audio playback
   * without requiring timers or recurring oscillator allocations.
   */
  _startCriticalLoop() {
    if (this.isCriticalPlaying) {
      console.log('[SoundManager] critical siren already active');
      return;
    }

    console.log('[SoundManager] starting critical siren');
    this.isCriticalPlaying = true;
    this.lastPlayedTier = 'critical';
    this.lastPlayTime = Date.now();

    // Haptic vibration feedback during critical alarm
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      try {
        navigator.vibrate([250, 100, 250, 100, 400]);
      } catch {}
    }

    const ctx = this._getAudioContext();
    if (!ctx) {
      console.warn('[SoundManager] AudioContext not available for critical siren');
      return;
    }

    // Ensure AudioContext is running
    if (ctx.state === 'suspended') {
      ctx.resume().then(() => {
        console.log('[SoundManager] AudioContext resumed for critical siren');
      }).catch((err) => {
        console.warn('[SoundManager] AudioContext resume error on critical siren:', err);
      });
    }

    try {
      const t0 = ctx.currentTime;

      // 1. Carrier Oscillator (Sawtooth tone sweeping between 480Hz and 960Hz)
      const carrierOsc = ctx.createOscillator();
      carrierOsc.type = 'sawtooth';
      carrierOsc.frequency.setValueAtTime(720, t0); // Base center frequency = 720 Hz

      // 2. LFO (Low-Frequency Oscillator) to modulate frequency continuously
      const lfoOsc = ctx.createOscillator();
      lfoOsc.type = 'triangle';
      lfoOsc.frequency.setValueAtTime(2.5, t0); // 2.5 sweeps per second

      // 3. LFO Gain (Modulation Depth: +/- 240 Hz -> sweeps 480 Hz to 960 Hz)
      const lfoGain = ctx.createGain();
      lfoGain.gain.setValueAtTime(240, t0);

      // Connect LFO -> Carrier Frequency Parameter
      lfoOsc.connect(lfoGain);
      lfoGain.connect(carrierOsc.frequency);

      // 4. Main Gain node for volume output
      const mainGain = ctx.createGain();
      mainGain.gain.setValueAtTime(0.50, t0);

      // Connect Carrier -> Main Gain -> Audio Destination
      carrierOsc.connect(mainGain);
      mainGain.connect(ctx.destination);

      // Start oscillators
      carrierOsc.start(t0);
      lfoOsc.start(t0);

      // Store node references for managed lifecycle
      this.criticalCarrierOsc = carrierOsc;
      this.criticalLfoOsc = lfoOsc;
      this.criticalLfoGain = lfoGain;
      this.criticalMainGain = mainGain;

      console.log('[SoundManager] Critical siren hardware nodes connected and running');
    } catch (err) {
      console.error('[SoundManager] Failed to start continuous critical siren:', err);
    }
  }

  /**
   * Stop the Level 3 critical siren immediately.
   */
  stopCriticalSiren() {
    if (!this.isCriticalPlaying && !this.criticalCarrierOsc) {
      return;
    }

    console.log('[SoundManager] stopping critical siren');
    this.isCriticalPlaying = false;

    if (this.criticalMainGain && this.audioCtx) {
      try {
        const t0 = this.audioCtx.currentTime;
        this.criticalMainGain.gain.setValueAtTime(this.criticalMainGain.gain.value, t0);
        this.criticalMainGain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.05);
      } catch {}
    }

    if (this.criticalCarrierOsc) {
      try {
        this.criticalCarrierOsc.stop();
        this.criticalCarrierOsc.disconnect();
      } catch {}
      this.criticalCarrierOsc = null;
    }

    if (this.criticalLfoOsc) {
      try {
        this.criticalLfoOsc.stop();
        this.criticalLfoOsc.disconnect();
      } catch {}
      this.criticalLfoOsc = null;
    }

    if (this.criticalLfoGain) {
      try {
        this.criticalLfoGain.disconnect();
      } catch {}
      this.criticalLfoGain = null;
    }

    if (this.criticalMainGain) {
      try {
        this.criticalMainGain.disconnect();
      } catch {}
      this.criticalMainGain = null;
    }
  }

  /**
   * Play alert sound according to tier and cooldown rules.
   *
   * Level 1 (Nudge): One-shot short beep (subject to cooldown)
   * Level 2 (Warning): One-shot warning pulse (subject to cooldown)
   * Level 3 (Critical): Continuous looping siren until alert tier leaves critical
   *
   * @param {'nudge' | 'warning' | 'critical' | null} tier
   * @param {boolean} force - If true, bypasses cooldown
   */
  playAlert(tier, force = false) {
    console.log(`[SoundManager] playAlert ${tier}`);
    if (!this.enabled) return;

    if (!tier) {
      // Alert cleared (Safe state) -> stop critical siren if active
      if (this.isCriticalPlaying) {
        this.stopCriticalSiren();
      }
      this.lastPlayedTier = null;
      return;
    }

    const normalizedTier = tier.toLowerCase();

    // 1. Level 3 Critical Alert: Continuous repeating siren
    if (normalizedTier === 'critical') {
      if (this.isCriticalPlaying) {
        console.log('[SoundManager] critical siren already active');
        return;
      }
      this._startCriticalLoop();
      return;
    }

    // 2. If entering non-critical (warning or nudge) while critical siren was playing, stop siren immediately
    if (this.isCriticalPlaying) {
      this.stopCriticalSiren();
    }

    const now = Date.now();
    const cooldown = this.cooldowns[normalizedTier] || 2500;
    const tierChanged = this.lastPlayedTier !== normalizedTier;
    const cooldownExpired = now - this.lastPlayTime >= cooldown;

    if (!force && !tierChanged && !cooldownExpired) {
      return;
    }

    this.lastPlayedTier = normalizedTier;
    this.lastPlayTime = now;

    // Haptic vibration feedback
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      try {
        if (normalizedTier === 'warning') {
          navigator.vibrate([180, 100, 180]);
        } else {
          navigator.vibrate(120);
        }
      } catch {}
    }

    const ctx = this._getAudioContext();
    if (!ctx) return;

    try {
      if (this.currentOscillator) {
        try {
          this.currentOscillator.stop();
          this.currentOscillator.disconnect();
        } catch {}
        this.currentOscillator = null;
      }

      const t0 = ctx.currentTime;
      const gain = ctx.createGain();
      gain.connect(ctx.destination);

      if (normalizedTier === 'warning') {
        // Level 2: Attention Two-Tone Pulse (One-shot)
        const osc = ctx.createOscillator();
        osc.type = 'square';
        osc.frequency.setValueAtTime(620, t0);
        osc.frequency.setValueAtTime(880, t0 + 0.16);

        gain.gain.setValueAtTime(0.30, t0);
        gain.gain.setValueAtTime(0.30, t0 + 0.30);
        gain.gain.exponentialRampToValueAtTime(0.01, t0 + 0.38);

        osc.connect(gain);
        osc.start(t0);
        osc.stop(t0 + 0.38);
        this.currentOscillator = osc;
        this.currentGain = gain;
      } else {
        // Level 1: Soft Warning Beep / Chime (One-shot)
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(784, t0); // G5 note
        osc.frequency.exponentialRampToValueAtTime(880, t0 + 0.15); // A5 note

        gain.gain.setValueAtTime(0.22, t0);
        gain.gain.exponentialRampToValueAtTime(0.01, t0 + 0.18);

        osc.connect(gain);
        osc.start(t0);
        osc.stop(t0 + 0.18);
        this.currentOscillator = osc;
        this.currentGain = gain;
      }
    } catch (err) {
      console.warn('[SoundManager] Audio alert generation error:', err);
    }
  }

  reset() {
    this.lastPlayedTier = null;
    this.lastPlayTime = 0;
    this.stop();
  }
}

export const soundManager = new SoundManager();
