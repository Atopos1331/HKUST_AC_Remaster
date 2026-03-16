# Control Strategy Guide

## Main Runtime Topology

The primary runtime starts from `controll.py` and currently runs:

- indoor climate polling thread
- control logic thread
- indoor and electrical recorder thread
- outdoor weather recorder thread
- QQ bot
- Discord bot

The control core lives in `powers/services/control_service.py`.

## Temperature Mode

Temperature mode uses these settings:

- `target_temp`
- `temperature_control_basis`
- `temp_threshold_high`
- `temp_threshold_low`
- `cooldown_time`

`temperature_control_basis` can be:

- `temperature`
- `heat_index`

That means the controller can operate either on dry-bulb temperature or on heat index.

Behavior:

- if AC is off and the current value is above `target_temp + temp_threshold_high`, request AC on
- if AC is on and the current value is below `target_temp - temp_threshold_low`, request AC off
- otherwise keep the current state

This is a hysteresis-based strategy to reduce flapping near the target.

## Cooldown

`cooldown_time` is one of the most important parameters in temperature mode.

It defines the minimum delay between two state transitions. During the cooldown window, the controller keeps the current state even if the live metric crosses a threshold again.

This helps:

- prevent frequent toggling
- reduce short-cycling
- give the room and the AC time to reflect the previous action

## Scheduler Mode

Scheduler mode ignores live indoor feedback and only uses:

- `ontime`
- `offtime`

Based on the current AC state and `last_switch`:

- if AC is on, it turns off after `ontime`
- if AC is off, it turns on after `offtime`

This mode is useful when:

- you do not have a reliable sensor
- the room has relatively stable thermal inertia
- you already know a workable on/off duty cycle

## Temporary Lock

The controller supports a temporary lock:

- `lock_status`
- `lock_end_time`

If the lock is still active, the control logic obeys the lock state before normal temperature-mode or scheduler-mode logic.

This is useful for:

- forcing AC on for a fixed period before sleep
- forcing AC off temporarily
- temporarily overriding the automatic policy

## Device Off-Timer as a Safety Guard

When the controller decides to turn the AC on, `ControlService.action()` also synchronizes the device-side off-timer.

That means the system does not only remember the intended next stop locally. It also writes a shutoff time into the AC-side timer. If the process exits unexpectedly, a thread hangs, or connectivity breaks, the hardware still keeps a fallback off-time.

## Master Switch and Balance Guard

Every control cycle in `controll.py` checks:

- the master `switch`
- the prepaid `balance`

If:

- the master switch is off, control actions are skipped
- the balance is depleted, control actions are skipped

This prevents unnecessary AC operations in obviously invalid states.