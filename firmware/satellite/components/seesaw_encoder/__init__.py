"""ESPHome component for the Adafruit I2C rotary encoder (seesaw firmware).

Reads rotation only. Each detent fires on_clockwise or on_anticlockwise once.

Example:

    i2c:
      sda: GPIO21
      scl: GPIO47

    seesaw_encoder:
      id: volume_knob
      address: 0x36
      on_clockwise:
        - media_player.volume_up: my_player
      on_anticlockwise:
        - media_player.volume_down: my_player
"""

from esphome import automation
import esphome.codegen as cg
from esphome.components import i2c
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_INVERTED

CODEOWNERS = ["@willsulli2004"]
DEPENDENCIES = ["i2c"]

CONF_ON_CLOCKWISE = "on_clockwise"
CONF_ON_ANTICLOCKWISE = "on_anticlockwise"

seesaw_encoder_ns = cg.esphome_ns.namespace("seesaw_encoder")
SeesawEncoder = seesaw_encoder_ns.class_(
    "SeesawEncoder", cg.PollingComponent, i2c.I2CDevice
)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SeesawEncoder),
            # Set true if turning clockwise fires on_anticlockwise.
            cv.Optional(CONF_INVERTED, default=False): cv.boolean,
            cv.Optional(CONF_ON_CLOCKWISE): automation.validate_automation({}),
            cv.Optional(CONF_ON_ANTICLOCKWISE): automation.validate_automation({}),
        }
    )
    .extend(cv.polling_component_schema("20ms"))
    .extend(i2c.i2c_device_schema(0x36))
)

_CALLBACK_AUTOMATIONS = (
    automation.CallbackAutomation(CONF_ON_CLOCKWISE, "add_on_clockwise_callback"),
    automation.CallbackAutomation(
        CONF_ON_ANTICLOCKWISE, "add_on_anticlockwise_callback"
    ),
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await i2c.register_i2c_device(var, config)
    cg.add(var.set_inverted(config[CONF_INVERTED]))
    await automation.build_callback_automations(var, config, _CALLBACK_AUTOMATIONS)
