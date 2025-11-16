import time
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

def get_user(user_id):
    """
    Retrieves a user from Firestore. If the user doesn't exist, it creates them.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user = user_ref.get()
    if not user.exists:
        user_ref.set({
            "bounty": 0,
            "berries": 500,
            "crew": [],
            "ship_id": None,
            "role": None,
            "daily_claim_timestamp": None,
            "bag": {},
            "hp": 100,
            "max_hp": 100,
            "duel_cooldown": None,
            "xp": 0,
            "last_chat_reward_timestamp": None,
            "last_reward_amount": 0,
            "chat_reward_cooldown_ends": None,
            "current_title": None,
            "unlocked_titles": [],
            "last_recruit_timestamp": None,
            "last_private_adventure_timestamp": None,
            "last_auction_claim_timestamp": None,
            "last_wanted_poster_timestamp": None
        })
        user = user_ref.get()
    return user.to_dict()

def update_berries(user_id, amount):
    """
    Atomically updates a user's berry count.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'berries': firestore.Increment(amount)
    })

def update_bounty(user_id, amount):
    """
    Atomically updates a user's bounty.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'bounty': firestore.Increment(amount)
    })

def update_spam_warnings(user_id, amount):
    """
    Atomically updates a user's spam warning count.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'spam_warnings': firestore.Increment(amount)
    })

def suspend_user(user_id, suspension_end_time):
    """
    Suspends a user and resets their spam warnings.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'suspended_until': suspension_end_time,
        'spam_warnings': 0
    })

def lift_suspension(user_id):
    """
    Lifts a user's suspension.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'suspended_until': firestore.DELETE_FIELD
    })

def add_to_crew(user_id, character_name):
    """
    Adds a character to a user's crew.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'crew': firestore.ArrayUnion([character_name])
    })

def reward_vote(user_id):
    """
    Gives a user 5,000 berries for voting.
    """
    try:
        update_berries(user_id, 5000)
        print(f"Successfully rewarded {user_id} with 5,000 berries for voting.")
    except Exception as e:
        print(f"An error occurred while rewarding {user_id} for voting: {e}")

def get_ship(ship_id):
    """
    Retrieves a ship from Firestore by its ID.
    """
    if not ship_id:
        return None
    ship_ref = db.collection('ships').document(str(ship_id))
    ship = ship_ref.get()
    return ship.to_dict() if ship.exists else None

def get_ship_by_name(name):
    """
    Retrieves a ship from Firestore by its name.
    """
    ships_ref = db.collection('ships')
    query = ships_ref.where('name', '==', name).limit(1)
    results = query.stream()
    for ship in results:
        return ship.to_dict()
    return None

def join_ship(user_id, ship_id):
    """
    Adds a user to a ship.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    ship_ref = db.collection('ships').document(str(ship_id))

    user_ref.update({
        'ship_id': ship_id,
        'role': 'member'
    })
    ship_ref.update({
        'members': firestore.ArrayUnion([str(user_id)])
    })

def leave_ship(user_id, ship_id):
    """
    Removes a user from a ship.
    """
    user_ref = db.collection('pirates').document(str(user_id))
    ship_ref = db.collection('ships').document(str(ship_id))

    user_ref.update({
        'ship_id': None,
        'role': None
    })
    ship_ref.update({
        'members': firestore.ArrayRemove([str(user_id)])
    })

@firestore.transactional
def _claim_daily_reward_transaction(transaction, user_ref, amount):
    transaction.update(user_ref, {
        'berries': firestore.Increment(amount),
        'daily_claim_timestamp': time.time()
    })

def claim_daily_reward(user_id, amount):
    user_ref = db.collection('pirates').document(str(user_id))
    transaction = db.transaction()
    _claim_daily_reward_transaction(transaction, user_ref, amount)

@firestore.transactional
def _gift_berries_transaction(transaction, sender_ref, recipient_ref, amount):
    sender_snapshot = sender_ref.get(transaction=transaction)
    if not sender_snapshot.exists or sender_snapshot.to_dict()['berries'] < amount:
        raise Exception("Insufficient berries.")

    recipient_snapshot = recipient_ref.get(transaction=transaction)
    if not recipient_snapshot.exists:
        raise Exception("Recipient not found.")

    transaction.update(sender_ref, {
        'berries': firestore.Increment(-amount)
    })
    transaction.update(recipient_ref, {
        'berries': firestore.Increment(amount)
    })

def gift_berries(sender_id, recipient_id, amount):
    sender_ref = db.collection('pirates').document(str(sender_id))
    recipient_ref = db.collection('pirates').document(str(recipient_id))
    transaction = db.transaction()
    _gift_berries_transaction(transaction, sender_ref, recipient_ref, amount)

@firestore.transactional
def _buy_item_transaction(transaction, user_ref, item_id, quantity, price):
    user_snapshot = user_ref.get(transaction=transaction)
    if not user_snapshot.exists or user_snapshot.to_dict()['berries'] < price * quantity:
        raise Exception("Insufficient berries.")

    transaction.update(user_ref, {
        'berries': firestore.Increment(-(price * quantity)),
        f'bag.{item_id}': firestore.Increment(quantity)
    })

def buy_item(user_id, item_id, quantity, price):
    user_ref = db.collection('pirates').document(str(user_id))
    transaction = db.transaction()
    _buy_item_transaction(transaction, user_ref, item_id, quantity, price)

@firestore.transactional
def _sell_item_transaction(transaction, user_ref, item_id, quantity, sell_price):
    user_snapshot = user_ref.get(transaction=transaction)
    if not user_snapshot.exists or user_snapshot.to_dict().get('bag', {}).get(item_id, 0) < quantity:
        raise Exception("You don't have enough of this item to sell.")

    transaction.update(user_ref, {
        'berries': firestore.Increment(sell_price * quantity),
        f'bag.{item_id}': firestore.Increment(-quantity)
    })

def sell_item(user_id, item_id, quantity, sell_price):
    user_ref = db.collection('pirates').document(str(user_id))
    transaction = db.transaction()
    _sell_item_transaction(transaction, user_ref, item_id, quantity, sell_price)


def add_ship_xp(ship_id, amount):
    """
    Atomically updates a ship's XP, checking for active events.
    """
    events_doc = db.collection('config').document('events').get()
    if events_doc.exists:
        events = events_doc.to_dict()
        if events.get('active_event') == "Double XP Day":
            amount *= 2

    ship_ref = db.collection('ships').document(str(ship_id))
    ship_ref.update({
        'xp': firestore.Increment(amount)
    })

@firestore.transactional
def _deposit_item_to_ship_transaction(transaction, user_ref, ship_ref, item_id, quantity):
    user_snapshot = user_ref.get(transaction=transaction)
    if not user_snapshot.exists or user_snapshot.to_dict().get('bag', {}).get(item_id, 0) < quantity:
        raise Exception("You don't have enough of this item.")

    ship_snapshot = ship_ref.get(transaction=transaction)
    if not ship_snapshot.exists:
        raise Exception("Ship not found.")
    
    ship_data = ship_snapshot.to_dict()
    current_storage = sum(ship_data.get('storage', {}).values())
    max_storage = ship_data.get('stats', {}).get('max_storage', 0)

    if current_storage + quantity > max_storage:
        raise Exception("Ship storage is full.")

    transaction.update(user_ref, {
        f'bag.{item_id}': firestore.Increment(-quantity)
    })
    transaction.update(ship_ref, {
        f'storage.{item_id}': firestore.Increment(quantity)
    })

def deposit_item_to_ship(user_id, ship_id, item_id, quantity):
    user_ref = db.collection('pirates').document(str(user_id))
    ship_ref = db.collection('ships').document(str(ship_id))
    transaction = db.transaction()
    _deposit_item_to_ship_transaction(transaction, user_ref, ship_ref, item_id, quantity)

@firestore.transactional
def _upgrade_ship_transaction(transaction, user_ref, ship_ref, upgrade_type, cost, new_level, new_stat_value):
    user_snapshot = user_ref.get(transaction=transaction)
    if not user_snapshot.exists or user_snapshot.to_dict()['berries'] < cost:
        raise Exception("Insufficient berries.")

    transaction.update(user_ref, {
        'berries': firestore.Increment(-cost)
    })

    if upgrade_type == 'hull':
        transaction.update(ship_ref, {
            'upgrades.hull_lvl': new_level,
            'stats.max_hp': new_stat_value,
            'hp': new_stat_value # also heal the ship to full hp
        })
    elif upgrade_type == 'storage':
        transaction.update(ship_ref, {
            'upgrades.storage_lvl': new_level,
            'stats.max_storage': new_stat_value
        })

def upgrade_ship(user_id, ship_id, upgrade_type, cost, new_level, new_stat_value):
    user_ref = db.collection('pirates').document(str(user_id))
    ship_ref = db.collection('ships').document(str(ship_id))
    transaction = db.transaction()
    _upgrade_ship_transaction(transaction, user_ref, ship_ref, upgrade_type, cost, new_level, new_stat_value)

@firestore.transactional
def _use_medical_kit_transaction(transaction, user_ref):
    user_snapshot = user_ref.get(transaction=transaction)
    user_data = user_snapshot.to_dict()

    if not user_snapshot.exists or user_data.get('bag', {}).get('medical_kit', 0) < 1:
        raise Exception("You don't have any medical kits.")

    if user_data.get('hp', 100) >= user_data.get('max_hp', 100):
        raise Exception("You are already at full health!")

    new_hp = min(user_data.get('hp', 100) + 50, user_data.get('max_hp', 100))

    transaction.update(user_ref, {
        'bag.medical_kit': firestore.Increment(-1),
        'hp': new_hp
    })

def use_medical_kit(user_id):
    user_ref = db.collection('pirates').document(str(user_id))
    transaction = db.transaction()
    _use_medical_kit_transaction(transaction, user_ref)

@firestore.transactional
def _escrow_wager_transaction(transaction, sender_ref, recipient_ref, wager):
    sender_snapshot = sender_ref.get(transaction=transaction)
    if not sender_snapshot.exists or sender_snapshot.to_dict()['berries'] < wager:
        raise Exception("You don't have enough berries for this wager.")

    recipient_snapshot = recipient_ref.get(transaction=transaction)
    if not recipient_snapshot.exists or recipient_snapshot.to_dict()['berries'] < wager:
        raise Exception(f"Recipient doesn't have enough berries for this wager.")

    transaction.update(sender_ref, {'berries': firestore.Increment(-wager)})
    transaction.update(recipient_ref, {'berries': firestore.Increment(-wager)})

def escrow_wager(sender_id, recipient_id, wager):
    sender_ref = db.collection('pirates').document(str(sender_id))
    recipient_ref = db.collection('pirates').document(str(recipient_id))
    transaction = db.transaction()
    _escrow_wager_transaction(transaction, sender_ref, recipient_ref, wager)

@firestore.transactional
def _resolve_duel_transaction(transaction, winner_ref, loser_ref, wager):
    transaction.update(winner_ref, {
        'berries': firestore.Increment(wager * 2),
        'duel_cooldown': time.time()
    })
    transaction.update(loser_ref, {
        'hp': 1,
        'duel_cooldown': time.time()
    })

def resolve_duel(winner_id, loser_id, wager):
    winner_ref = db.collection('pirates').document(str(winner_id))
    loser_ref = db.collection('pirates').document(str(loser_id))
    transaction = db.transaction()
    _resolve_duel_transaction(transaction, winner_ref, loser_ref, wager)

def set_war_cooldown(ship1_id, ship2_id):
    ship1_ref = db.collection('ships').document(str(ship1_id))
    ship2_ref = db.collection('ships').document(str(ship2_id))
    cooldown_time = time.time()
    ship1_ref.update({'war_cooldown': cooldown_time})
    ship2_ref.update({'war_cooldown': cooldown_time})

@firestore.transactional
def _resolve_ship_war_transaction(transaction, winner_captain_ref, winner_ship_ref, loser_ship_ref, wager, winner_xp_gain, loser_item_loss):
    transaction.update(winner_captain_ref, {
        'berries': firestore.Increment(wager * 2)
    })
    transaction.update(winner_ship_ref, {
        'xp': firestore.Increment(winner_xp_gain)
    })
    if loser_item_loss:
        loser_ship_snapshot = loser_ship_ref.get(transaction=transaction)
        loser_ship_data = loser_ship_snapshot.to_dict()
        storage = loser_ship_data.get('storage', {})
        if storage:
            item_to_remove = list(storage.keys())[0]
            amount_to_remove = math.ceil(storage[item_to_remove] * 0.1)
            transaction.update(loser_ship_ref, {
                f'storage.{item_to_remove}': firestore.Increment(-amount_to_remove)
            })

    # Chance for equipment degradation
    if random.random() < 0.2: # 20% chance to degrade equipment
        loser_ship_snapshot = loser_ship_ref.get(transaction=transaction)
        loser_ship_data = loser_ship_snapshot.to_dict()
        upgrades = loser_ship_data.get('upgrades', {})

        degrade_type = random.choice(['hull_lvl', 'cannon_lvl'])
        current_level = upgrades.get(degrade_type, 1)

        if current_level > 1:
            new_level = current_level - 1
            transaction.update(loser_ship_ref, {f'upgrades.{degrade_type}': new_level})

def resolve_ship_war(winner_captain_id, winner_ship_id, loser_ship_id, wager, winner_xp_gain, loser_item_loss):
    winner_captain_ref = db.collection('pirates').document(str(winner_captain_id))
    winner_ship_ref = db.collection('ships').document(str(winner_ship_id))
    loser_ship_ref = db.collection('ships').document(str(loser_ship_id))
    transaction = db.transaction()
    _resolve_ship_war_transaction(transaction, winner_captain_ref, winner_ship_ref, loser_ship_ref, wager, winner_xp_gain, loser_item_loss)

@firestore.transactional
def _repair_ship_transaction(transaction, ship_ref, tools_needed, hp_to_heal):
    ship_snapshot = ship_ref.get(transaction=transaction)
    ship_data = ship_snapshot.to_dict()

    if not ship_snapshot.exists or ship_data.get('storage', {}).get('repair_tool', 0) < tools_needed:
        raise Exception("Not enough repair tools in the ship's storage.")

    transaction.update(ship_ref, {
        'storage.repair_tool': firestore.Increment(-tools_needed),
        'hp': firestore.Increment(hp_to_heal)
    })

def repair_ship(ship_id, tools_needed, hp_to_heal):
    ship_ref = db.collection('ships').document(str(ship_id))
    transaction = db.transaction()
    _repair_ship_transaction(transaction, ship_ref, tools_needed, hp_to_heal)

@firestore.transactional
def _create_auction_transaction(transaction, user_ref, item_type, item_id, item_name, quantity, seller_name, starting_bid):
    user_snapshot = user_ref.get(transaction=transaction)
    user_data = user_snapshot.to_dict()

    if item_type == 'item':
        if user_data.get('bag', {}).get(item_id, 0) < quantity:
            raise Exception("You don't have enough of this item to sell.")
        transaction.update(user_ref, {f'bag.{item_id}': firestore.Increment(-quantity)})
    elif item_type == 'crew':
        if item_id not in user_data.get('crew', []):
            raise Exception("You don't have this crew member.")
        transaction.update(user_ref, {'crew': firestore.ArrayRemove([item_id])})
    else:
        raise Exception("Invalid item type.")

    # Create new auction document
    auction_ref = db.collection('auctions').document()
    transaction.set(auction_ref, {
        "item_id": item_id,
        "item_name": item_name,
        "item_type": item_type,
        "quantity": quantity,
        "seller_id": user_snapshot.id,
        "seller_name": seller_name,
        "starting_bid": starting_bid,
        "current_bid": starting_bid,
        "highest_bidder_id": None,
        "end_time": time.time() + 86400 # 24 hours
    })
    return auction_ref.id

def create_auction(seller_id, item_type, item_id, item_name, quantity, seller_name, starting_bid):
    user_ref = db.collection('pirates').document(str(seller_id))
    transaction = db.transaction()
    return _create_auction_transaction(transaction, user_ref, item_type, item_id, item_name, quantity, seller_name, starting_bid)

@firestore.transactional
def _bid_on_auction_transaction(transaction, bidder_ref, auction_ref, bid_amount):
    auction_snapshot = auction_ref.get(transaction=transaction)
    auction_data = auction_snapshot.to_dict()

    if not auction_snapshot.exists:
        raise Exception("Auction not found.")

    if auction_data['end_time'] <= time.time():
        raise Exception("This auction has already ended.")

    bidder_snapshot = bidder_ref.get(transaction=transaction)
    if not bidder_snapshot.exists or bidder_snapshot.to_dict()['berries'] < bid_amount:
        raise Exception("Insufficient berries.")

    if bid_amount <= auction_data['current_bid']:
        raise Exception("Your bid must be higher than the current bid.")

    # Refund previous bidder
    if auction_data['highest_bidder_id']:
        previous_bidder_ref = db.collection('pirates').document(str(auction_data['highest_bidder_id']))
        transaction.update(previous_bidder_ref, {'berries': firestore.Increment(auction_data['current_bid'])})

    # Escrow new bid
    transaction.update(bidder_ref, {'berries': firestore.Increment(-bid_amount)})

    # Update auction
    transaction.update(auction_ref, {
        'current_bid': bid_amount,
        'highest_bidder_id': bidder_snapshot.id
    })

def bid_on_auction(bidder_id, auction_id, bid_amount):
    bidder_ref = db.collection('pirates').document(str(bidder_id))
    auction_ref = db.collection('auctions').document(str(auction_id))
    transaction = db.transaction()
    _bid_on_auction_transaction(transaction, bidder_ref, auction_ref, bid_amount)

@firestore.transactional
def _claim_sold_auction_transaction(transaction, seller_ref, auction_ref):
    auction_snapshot = auction_ref.get(transaction=transaction)
    auction_data = auction_snapshot.to_dict()

    payout = math.floor(auction_data['current_bid'] * 0.95)
    transaction.update(seller_ref, {'berries': firestore.Increment(payout)})
    transaction.delete(auction_ref)
    return payout

def claim_sold_auction(seller_id, auction_id):
    seller_ref = db.collection('pirates').document(str(seller_id))
    auction_ref = db.collection('auctions').document(str(auction_id))
    transaction = db.transaction()
    return _claim_sold_auction_transaction(transaction, seller_ref, auction_ref)

@firestore.transactional
def _claim_won_auction_transaction(transaction, winner_ref, auction_ref):
    auction_snapshot = auction_ref.get(transaction=transaction)
    auction_data = auction_snapshot.to_dict()

    item_type = auction_data['item_type']
    item_id = auction_data['item_id']
    quantity = auction_data['quantity']

    if item_type == 'item':
        transaction.update(winner_ref, {f'bag.{item_id}': firestore.Increment(quantity)})
    elif item_type == 'crew':
        transaction.update(winner_ref, {'crew': firestore.ArrayUnion([item_id])})
        
    transaction.delete(auction_ref)

def claim_won_auction(winner_id, auction_id):
    winner_ref = db.collection('pirates').document(str(winner_id))
    auction_ref = db.collection('auctions').document(str(auction_id))
    transaction = db.transaction()
    _claim_won_auction_transaction(transaction, winner_ref, auction_ref)

@firestore.transactional
def _grant_chat_reward_transaction(transaction, user_ref, berry_reward, xp_reward):
    cooldown_end_time = time.time() + 120
    transaction.update(user_ref, {
        'berries': firestore.Increment(berry_reward),
        'xp': firestore.Increment(xp_reward),
        'last_chat_reward_timestamp': time.time(),
        'last_reward_amount': berry_reward,
        'chat_reward_cooldown_ends': cooldown_end_time
    })

def grant_chat_reward(user_id, berry_reward, xp_reward):
    user_ref = db.collection('pirates').document(str(user_id))
    transaction = db.transaction()
    _grant_chat_reward_transaction(transaction, user_ref, berry_reward, xp_reward)

@firestore.transactional
def _buy_title_transaction(transaction, user_ref, title, price):
    user_snapshot = user_ref.get(transaction=transaction)
    user_data = user_snapshot.to_dict()

    if not user_snapshot.exists or user_data.get('berries', 0) < price:
        raise Exception("Insufficient berries.")
        
    if title in user_data.get('unlocked_titles', []):
        raise Exception("You have already unlocked this title.")

    transaction.update(user_ref, {
        'berries': firestore.Increment(-price),
        'unlocked_titles': firestore.ArrayUnion([title])
    })

def buy_title(user_id, title, price):
    user_ref = db.collection('pirates').document(str(user_id))
    transaction = db.transaction()
    _buy_title_transaction(transaction, user_ref, title, price)

def equip_title(user_id, title):
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({'current_title': title})

@firestore.transactional
def _equip_badge_transaction(transaction, user_ref, ship_ref, badge_id):
    user_snapshot = user_ref.get(transaction=transaction)
    user_data = user_snapshot.to_dict()

    if not user_snapshot.exists or user_data.get('bag', {}).get(badge_id, 0) < 1:
        raise Exception("You don't own this badge.")

    transaction.update(user_ref, {f'bag.{badge_id}': firestore.Increment(-1)})
    transaction.update(ship_ref, {'equipped_badge': badge_id})

def equip_badge(user_id, ship_id, badge_id):
    user_ref = db.collection('pirates').document(str(user_id))
    ship_ref = db.collection('ships').document(str(ship_id))
    transaction = db.transaction()
    _equip_badge_transaction(transaction, user_ref, ship_ref, badge_id)

@firestore.transactional
def _unequip_badge_transaction(transaction, user_ref, ship_ref, badge_id):
    transaction.update(user_ref, {f'bag.{badge_id}': firestore.Increment(1)})
    transaction.update(ship_ref, {'equipped_badge': None})

def unequip_badge(user_id, ship_id, badge_id):
    user_ref = db.collection('pirates').document(str(user_id))
    ship_ref = db.collection('ships').document(str(ship_id))
    transaction = db.transaction()
    _unequip_badge_transaction(transaction, user_ref, ship_ref, badge_id)

def update_recruit_cooldown(user_id):
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'last_recruit_timestamp': time.time()
    })

def update_private_adventure_cooldown(user_id):
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'last_private_adventure_timestamp': time.time()
    })

def update_auction_claim_cooldown(user_id):
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'last_auction_claim_timestamp': time.time()
    })

def update_wanted_poster_cooldown(user_id):
    user_ref = db.collection('pirates').document(str(user_id))
    user_ref.update({
        'last_wanted_poster_timestamp': time.time()
    })
