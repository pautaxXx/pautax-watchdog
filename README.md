# pautax-watchdog

An external dead-man's switch for a trading computer. The computer posts a heartbeat to a private
push-notification topic every 5 minutes; this GitHub Actions job checks it every 5 minutes during US
market hours and pushes an urgent phone alert when the heartbeat stops. No brokerage access, no keys:
the only secrets are the two topic names.
