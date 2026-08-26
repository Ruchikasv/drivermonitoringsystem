import test from 'node:test';
import assert from 'node:assert/strict';
import { SoundManager } from './soundManager.js';

// Setup Mock Web Audio Environment for headless testing
function setupMockAudioEnv() {
  let createdOscillators = 0;
  let createdGains = 0;

  class MockAudioParam {
    constructor() {
      this.value = 0;
    }
    setValueAtTime(val) { this.value = val; }
    linearRampToValueAtTime(val) { this.value = val; }
    exponentialRampToValueAtTime(val) { this.value = val; }
  }

  class MockOscillator {
    constructor() {
      this.type = 'sine';
      this.frequency = new MockAudioParam();
      this.started = false;
      this.stopped = false;
      this.connected = false;
      createdOscillators++;
    }
    connect() { this.connected = true; }
    disconnect() { this.connected = false; }
    start() { this.started = true; }
    stop() { this.stopped = true; }
  }

  class MockGain {
    constructor() {
      this.gain = new MockAudioParam();
      this.connected = false;
      createdGains++;
    }
    connect() { this.connected = true; }
    disconnect() { this.connected = false; }
  }

  class MockAudioContext {
    constructor() {
      this.state = 'running';
      this.currentTime = 100.0;
      this.destination = {};
    }
    resume() {
      this.state = 'running';
      return Promise.resolve();
    }
    createOscillator() {
      return new MockOscillator();
    }
    createGain() {
      return new MockGain();
    }
  }

  globalThis.window = {
    AudioContext: MockAudioContext,
  };
  try {
    globalThis.navigator.vibrate = () => {};
  } catch {
    Object.defineProperty(globalThis, 'navigator', {
      value: { vibrate: () => {} },
      configurable: true,
      writable: true,
    });
  }

  return {
    getOscillatorCount: () => createdOscillators,
    getGainCount: () => createdGains,
  };
}

test('SoundManager - Level 3 Critical Audio Lifecycle & Transitions', async (t) => {
  setupMockAudioEnv();

  await t.test('1. Critical alert starts continuous siren hardware nodes', () => {
    const sm = new SoundManager();
    assert.equal(sm.isCriticalPlaying, false);

    sm.playAlert('critical');
    assert.equal(sm.isCriticalPlaying, true);
    assert.equal(sm.lastPlayedTier, 'critical');
    assert.notEqual(sm.criticalCarrierOsc, null);
    assert.notEqual(sm.criticalLfoOsc, null);

    sm.stop();
  });

  await t.test('2. Repeated renders / frame updates do not create multiple overlapping sirens', () => {
    const sm = new SoundManager();
    sm.playAlert('critical');
    const initialCarrier = sm.criticalCarrierOsc;

    // Simulate 20 consecutive video frames in Level 3 Critical
    for (let i = 0; i < 20; i++) {
      sm.playAlert('critical');
    }

    assert.equal(sm.isCriticalPlaying, true);
    // Ensure the hardware node was not recreated or duplicated
    assert.equal(sm.criticalCarrierOsc, initialCarrier);

    sm.stop();
  });

  await t.test('3. Critical persists -> siren continues running', async () => {
    const sm = new SoundManager();
    sm.playAlert('critical');
    assert.equal(sm.isCriticalPlaying, true);

    // Verify after elapsed time that critical status is still playing
    await new Promise((resolve) => setTimeout(resolve, 50));
    assert.equal(sm.isCriticalPlaying, true);
    assert.notEqual(sm.criticalCarrierOsc, null);

    sm.stop();
  });

  await t.test('4. Critical -> Warning -> siren stops immediately and warning sound triggers', () => {
    const sm = new SoundManager();
    sm.playAlert('critical');
    assert.equal(sm.isCriticalPlaying, true);

    // Driver state de-escalates to Warning
    sm.playAlert('warning');
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null);
    assert.equal(sm.lastPlayedTier, 'warning');

    sm.stop();
  });

  await t.test('5. Critical -> Safe (null) -> siren stops immediately', () => {
    const sm = new SoundManager();
    sm.playAlert('critical');
    assert.equal(sm.isCriticalPlaying, true);

    // Driver opens eyes and recovers -> backend returns null alert
    sm.playAlert(null);
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null);
    assert.equal(sm.lastPlayedTier, null);

    sm.stop();
  });

  await t.test('6. Pause trip -> siren stops immediately', () => {
    const sm = new SoundManager();
    sm.playAlert('critical');
    assert.equal(sm.isCriticalPlaying, true);

    // Driver pauses trip
    sm.stop();
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null);
    assert.equal(sm.currentOscillator, null);
  });

  await t.test('7. End trip -> siren stops immediately', () => {
    const sm = new SoundManager();
    sm.playAlert('critical');
    assert.equal(sm.isCriticalPlaying, true);

    // Driver ends trip
    sm.stop();
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null);
    assert.equal(sm.currentOscillator, null);
  });

  await t.test('8. Level 1 Nudge and Level 2 Warning remain one-shot (not continuous loops)', () => {
    const sm = new SoundManager();

    // Nudge
    sm.playAlert('nudge');
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null);
    assert.equal(sm.lastPlayedTier, 'nudge');

    // Warning
    sm.playAlert('warning', true);
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null);
    assert.equal(sm.lastPlayedTier, 'warning');

    sm.stop();
  });

  await t.test('9. Critical remains active across frames where alert payload is null, siren continues until recovery', () => {
    const sm = new SoundManager();

    // Helper simulating DriverMonitoringPage.jsx onmessage logic
    function handleTelemetryFrame(frameData) {
      const isCriticalActive = Boolean(frameData.critical_active) && !frameData.is_paused;
      if (isCriticalActive) {
        sm.playAlert('critical');
      } else {
        if (sm.isCriticalPlaying) {
          sm.stopCriticalSiren();
        }
        if (frameData.alert && !frameData.is_paused) {
          if (frameData.alert.tier === 'warning') sm.playAlert('warning');
          else if (frameData.alert.tier === 'nudge') sm.playAlert('nudge');
        }
      }
    }

    // Frame 1: Critical incident triggered
    handleTelemetryFrame({ critical_active: true, alert: { tier: 'critical', message: 'Pull over' }, is_paused: false });
    assert.equal(sm.isCriticalPlaying, true);
    const carrierInstance = sm.criticalCarrierOsc;
    assert.notEqual(carrierInstance, null);

    // Frames 2..15: Subsequent frames while eyes are still closed (alert is null to prevent spam, but critical_active is true)
    for (let f = 2; f <= 15; f++) {
      handleTelemetryFrame({ critical_active: true, alert: null, is_paused: false });
      assert.equal(sm.isCriticalPlaying, true);
      assert.equal(sm.criticalCarrierOsc, carrierInstance); // Same carrier node, no duplicate creation
    }

    // Frame 16: Driver genuinely opens eyes / recovers (critical_active becomes false)
    handleTelemetryFrame({ critical_active: false, alert: null, is_paused: false });
    assert.equal(sm.isCriticalPlaying, false);
    assert.equal(sm.criticalCarrierOsc, null); // Siren stopped immediately

    sm.stop();
  });
});
