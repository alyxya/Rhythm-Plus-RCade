import './style.css'
import { PLAYER_1, SYSTEM } from '@rcade/plugin-input-classic'

// RCade input integration for Rhythm+
// The game's main logic is in the bundled assets/index-*.js file
// This file provides the bridge between RCade arcade controls and keyboard events

// Map RCade controls to keyboard events that Rhythm+ expects
const keyMap = {
  up: 'ArrowUp',
  down: 'ArrowDown',
  left: 'ArrowLeft',
  right: 'ArrowRight',
  A: 'KeyD',      // Primary action
  B: 'KeyF',      // Secondary action
}

const activeKeys = new Set()

function simulateKeyEvent(key, type) {
  const event = new KeyboardEvent(type, {
    key: key,
    code: key,
    bubbles: true,
    cancelable: true
  })
  document.dispatchEvent(event)
}

function update() {
  // D-pad controls
  const dpadState = {
    up: PLAYER_1.DPAD.up,
    down: PLAYER_1.DPAD.down,
    left: PLAYER_1.DPAD.left,
    right: PLAYER_1.DPAD.right,
  }

  // Button controls
  const buttonState = {
    A: PLAYER_1.A,
    B: PLAYER_1.B,
  }

  // Handle D-pad
  for (const [direction, key] of Object.entries(keyMap)) {
    if (direction === 'A' || direction === 'B') continue

    const isPressed = dpadState[direction]
    const wasPressed = activeKeys.has(direction)

    if (isPressed && !wasPressed) {
      activeKeys.add(direction)
      simulateKeyEvent(key, 'keydown')
    } else if (!isPressed && wasPressed) {
      activeKeys.delete(direction)
      simulateKeyEvent(key, 'keyup')
    }
  }

  // Handle buttons
  for (const button of ['A', 'B']) {
    const isPressed = buttonState[button]
    const wasPressed = activeKeys.has(button)

    if (isPressed && !wasPressed) {
      activeKeys.add(button)
      simulateKeyEvent(keyMap[button], 'keydown')
    } else if (!isPressed && wasPressed) {
      activeKeys.delete(button)
      simulateKeyEvent(keyMap[button], 'keyup')
    }
  }

  // Handle 1P Start (could be used for menu navigation)
  if (SYSTEM.ONE_PLAYER) {
    simulateKeyEvent('Enter', 'keydown')
    setTimeout(() => simulateKeyEvent('Enter', 'keyup'), 100)
  }

  requestAnimationFrame(update)
}

update()
