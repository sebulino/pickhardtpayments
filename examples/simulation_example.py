from pickhardtpayments.Payment import logger
from pickhardtpayments.ChannelGraph import ChannelGraph
from pickhardtpayments.UncertaintyNetwork import UncertaintyNetwork
from pickhardtpayments.OracleLightningNetwork import OracleLightningNetwork
from pickhardtpayments.SyncSimulatedPaymentSession import SyncSimulatedPaymentSession

import logging
import random
import ndjson


logger.info('*** new payment simulation ***')

# *** Setup ***
# + Definition of network that serves as OracleLightningNetwork
# channel_graph = ChannelGraph("listchannels20220412.json")
channel_graph = ChannelGraph("channels.sample.json")
# clean_channel_graph = channel_graph.only_channels_with_return_channels()
uncertainty_network = UncertaintyNetwork(channel_graph)
# uncertainty_network = UncertaintyNetwork(clean_channel_graph)
oracle_lightning_network = OracleLightningNetwork(channel_graph)
# oracle_lightning_network = OracleLightningNetwork(clean_channel_graph)


nodes = {}

# + Definition of number of payments to be sent
number_of_payments = 20  # TODO how to decide on number of runs?

# + Definition of distribution of payment amounts
mean_payment_amount = 10_000


def payment_amount(amount=10_000_000) -> int:
    # TODO randomize payment amount if needed
    return amount


# + Definition of Strategies that the sending nodes act upon
def assign_strategy_to_nodes(node):
    """
    This method serves as a filter before choosing the path finding algorithm in '_generate_candidate_paths'.
    Currently, the only path finding algorithm used in the simulation is min_cost_flow.
    But the development goal is to have a switch as to how the paths for the onion are selected.
    This creates a state machine that allows to switch strategies.
    """
    # nodes is the set of nodes
    # node is the key
    # value is a tuple, consisting of current strategy ID and the number of rounds that the strategy has been used
    # a threshold can advance the strategy after a number of times the strategy has been called
    number_of_strategies = 2
    number_of_turns_before_strategy_rotation = 5
    if node not in nodes:
        nodes[node][0] = 0
        nodes[node][1] = 1
    else:
        logging.info('node found, strategy is %s', nodes[node][0])
        if nodes[node][1] % number_of_turns_before_strategy_rotation:
            nodes[node][1] += 1
        else:
            nodes[node][0] = (nodes[node][0] + 1) % number_of_strategies  # assuming two possible strategies
            nodes[node][1] = 0


def create_payment_set(_uncertainty_network, _number_of_payments, amount) -> list[dict]:
    if (len(_uncertainty_network.network.nodes())) < 3:
        logging.warning("graph has less than two nodes")
        exit(-1)
    _payments = []
    while len(_payments) < _number_of_payments:
        # casting _channel_graph to list to avoid deprecation warning for python 3.9
        _random_nodes = random.sample(list(_uncertainty_network.network.nodes), 2)
        # additional check for existence; doing it here avoids the check in each round, improving runtime
        src_exists = _random_nodes[0] in _uncertainty_network.network.nodes()
        dest_exists = _random_nodes[1] in _uncertainty_network.network.nodes()
        if src_exists and dest_exists:
            p = {"sender": _random_nodes[0], "receiver": _random_nodes[1], "amount": payment_amount(amount)}
            _payments.append(p)
    # write payments to file
    ndjson.dump(_payments, open("examples/payments_small_graph.ndjson", "w"))
    return _payments


# + Creation of a collection of N payments (src, rcv, amount)
# payments = create_payment_set(uncertainty_network, number_of_payments, mean_payment_amount)
payment_set = ndjson.load(open("examples/same_payments_small_graph.ndjson", "r"))
logging.debug("Payments:\n%s", ndjson.dumps(payment_set))
logger.info("A total of {} payments.".format(len(payment_set)))

# set level of verbosity
loglevel = "info"
numeric_level = logging.getLevelName(loglevel.upper())
if not isinstance(numeric_level, int):
    raise ValueError('Invalid log level: %s' % loglevel)
logger.setLevel(numeric_level)

# start simulation
c = 0
successful_payments = 0
failed_payments = 0
payment_simulation = []

# create new payment session - will later be moved before payment loop to simulate sequence of payments
sim_session = SyncSimulatedPaymentSession(oracle_lightning_network, uncertainty_network, prune_network=False)


for payment in payment_set:
    c += 1
    # create new payment session
    # sim_session = SyncSimulatedPaymentSession(oracle_lightning_network, uncertainty_network, prune_network=False)
    # we need to make sure we forget all learnt information on the Uncertainty Network
    # sim_session.forget_information()
    logger.info("*********** Payment {} ***********".format(c))
    logger.debug(f"now sending {payment['amount']} sats from {payment['sender']} to {payment['receiver']}")

    ret = sim_session.pickhardt_pay(payment["sender"], payment["receiver"], payment["amount"],
                                    mu=0, base=0, loglevel=loglevel)
    if ret > 0:
        successful_payments += 1
        logger.debug("Payment in run {} was successful.".format(c))
    if ret < 0:
        failed_payments += 1
        logger.info("Payment in run {} failed.".format(c))
    payment['success'] = ret
    payment_simulation.append(payment)

ndjson.dump(payment_simulation, open("examples/payment_sim.ndjson", "w"))
print(f"\n{c} payments. {successful_payments} successful, {failed_payments} failed.")
