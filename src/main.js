import './style.css'
import { PLAYER_1, PLAYER_2, SYSTEM } from '@rcade/plugin-input-classic'

// RCade input integration for Rhythm+
// The game's main logic is in the bundled assets/index-*.js file
// This file provides the bridge between RCade arcade controls and game input

// Track which inputs are currently active (to detect press/release)
const activeInputs = new Set()

// Dispatch custom RCade key events that the game engine listens for
function dispatchRcadeKeyEvent(key, type) {
  const event = new CustomEvent(`rcade-${type}`, {
    detail: { key: key },
    bubbles: true
  })
  window.dispatchEvent(event)
}

// Dispatch custom RCade button events for UI/menu handling
function dispatchRcadeButtonEvent(buttonName) {
  const event = new CustomEvent(`rcade-button-${buttonName.toLowerCase()}`, {
    detail: { button: buttonName },
    bubbles: true
  })
  window.dispatchEvent(event)
}

function handleInput(inputName, isPressed, key) {
  const wasPressed = activeInputs.has(inputName)

  if (isPressed && !wasPressed) {
    activeInputs.add(inputName)
    dispatchRcadeKeyEvent(key, 'keydown')
    dispatchRcadeButtonEvent(inputName)
  } else if (!isPressed && wasPressed) {
    activeInputs.delete(inputName)
    dispatchRcadeKeyEvent(key, 'keyup')
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
  handleInput('up', PLAYER_1.DPAD.up || PLAYER_2.DPAD.up, 'ArrowUp')
  handleInput('down', PLAYER_1.DPAD.down || PLAYER_2.DPAD.down, 'ArrowDown')
  handleInput('left', PLAYER_1.DPAD.left || PLAYER_2.DPAD.left, 'ArrowLeft')
  handleInput('right', PLAYER_1.DPAD.right || PLAYER_2.DPAD.right, 'ArrowRight')

  // System start buttons
  handleInput('start', SYSTEM.ONE_PLAYER || SYSTEM.TWO_PLAYER, 'Enter')

  requestAnimationFrame(update)
}

update()
