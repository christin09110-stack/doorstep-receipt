"""Every test runs with Bedrock stubbed out, deliberately.

The upgrade brief's rule is that every model call needs a test that passes with
the call stubbed. The way to be sure of that is to make the stub the default for
the whole suite: no test reaches AWS, the suite runs on a plane, and a test that
wants to exercise a Bedrock path has to hand in its own ``StubRunner`` with a
canned reply, which makes the model's contribution visible in the test itself.

A ``StubRunner`` with an empty queue raises ``BedrockUnavailable``, so the
default here is also the offline case: anything that calls a model without
arranging a reply is exercising the fallback path, which is exactly what should
happen when nobody has set up a reply.
"""

import pytest

from doorstep_receipt import bedrock


@pytest.fixture(autouse=True)
def _no_network_bedrock():
    bedrock.set_default_runner(bedrock.StubRunner(model_id="stub (tests)"))
    yield
    bedrock.set_default_runner(None)
