import './style.css'
import { PLAYER_1, PLAYER_2, SYSTEM } from '@rcade/plugin-input-classic'

// RCade input integration for Rhythm+
// The game's main logic is in the bundled assets/index-*.js file
// This file provides the bridge between RCade arcade controls and keyboard events

// Track which inputs are currently active (to detect press/release)
const activeInputs = new Set()

// Hold-to-repeat configuration for D-pad navigation
const holdRepeatConfig = {
  initialDelay: 400,  // ms before repeat starts
  repeatInterval: 150 // ms between repeats
}

// Track hold state for repeatable inputs
const holdState = {}

function startHoldRepeat(inputName) {
  if (holdState[inputName]) return

  holdState[inputName] = {
    startTime: Date.now(),
    repeatStarted: false,
    intervalId: null
  }

  // After initial delay, start repeating
  holdState[inputName].timeoutId = setTimeout(() => {
    if (!holdState[inputName]) return
    holdState[inputName].repeatStarted = true

    // Dispatch immediately when repeat starts
    dispatchRcadeEvent(inputName)

    // Then continue at repeat interval
    holdState[inputName].intervalId = setInterval(() => {
      if (holdState[inputName]) {
        dispatchRcadeEvent(inputName)
      }
    }, holdRepeatConfig.repeatInterval)
  }, holdRepeatConfig.initialDelay)
}

function stopHoldRepeat(inputName) {
  if (!holdState[inputName]) return

  if (holdState[inputName].timeoutId) {
    clearTimeout(holdState[inputName].timeoutId)
  }
  if (holdState[inputName].intervalId) {
    clearInterval(holdState[inputName].intervalId)
  }
  delete holdState[inputName]
}

function simulateKeyEvent(key, type) {
  // Try direct game engine call first (works in RCade sandbox)
  if (window.__rcadeGameEngine) {
    if (type === 'keydown') {
      window.__rcadeGameEngine.onKeyDown(key)
    } else if (type === 'keyup') {
      window.__rcadeGameEngine.onKeyUp(key)
    }
    return
  }
  // Fallback to keyboard event (works in dev mode)
  const event = new KeyboardEvent(type, {
    key: key,
    code: 'Key' + key.toUpperCase(),
    bubbles: true,
    cancelable: true
  })
  document.dispatchEvent(event)
}

// Dispatch custom RCade button events for UI/menu handling
function dispatchRcadeEvent(buttonName) {
  const event = new CustomEvent(`rcade-button-${buttonName.toLowerCase()}`, {
    detail: { button: buttonName },
    bubbles: true
  })
  window.dispatchEvent(event)
}

function handleInput(inputName, isPressed, key, enableHoldRepeat = false) {
  const wasPressed = activeInputs.has(inputName)

  if (isPressed && !wasPressed) {
    activeInputs.add(inputName)
    // Always dispatch button event for UI handlers
    dispatchRcadeEvent(inputName)
    // Then handle gameplay input
    simulateKeyEvent(key, 'keydown')
    // Start hold-repeat timer if enabled for this input
    if (enableHoldRepeat) {
      startHoldRepeat(inputName)
    }
  } else if (!isPressed && wasPressed) {
    activeInputs.delete(inputName)
    simulateKeyEvent(key, 'keyup')
    // Stop hold-repeat if it was active
    if (enableHoldRepeat) {
      stopHoldRepeat(inputName)
    }
  }
}

function update() {
  // Gameplay buttons - 4 keys for 4-track rhythm game (1, 2, 3, 4)
  // P1 controls left side (tracks 1-2), P2 controls right side (tracks 3-4)
  handleInput('p1-a', PLAYER_1.A, '1')
  handleInput('p1-b', PLAYER_1.B, '2')
  handleInput('p2-a', PLAYER_2.A, '3')
  handleInput('p2-b', PLAYER_2.B, '4')

  // D-pad - combine both players for menu navigation
  // Enable hold-repeat for up/down to allow continuous scrolling through song list
  handleInput('up', PLAYER_1.DPAD.up || PLAYER_2.DPAD.up, 'ArrowUp', true)
  handleInput('down', PLAYER_1.DPAD.down || PLAYER_2.DPAD.down, 'ArrowDown', true)
  handleInput('left', PLAYER_1.DPAD.left || PLAYER_2.DPAD.left, 'ArrowLeft')
  handleInput('right', PLAYER_1.DPAD.right || PLAYER_2.DPAD.right, 'ArrowRight')

  // System start buttons
  handleInput('start', SYSTEM.ONE_PLAYER || SYSTEM.TWO_PLAYER, 'Enter')

  requestAnimationFrame(update)
}

update()
