import pygame
import random
from pygame.locals import *

# Card class
class Card:
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    ranks = ['ace', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'jack', 'queen', 'king']
    rank_values = {'ace':1, '2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, '10':10, 'jack':10, 'queen':10, 'king':10}
    rank_order = {'ace':1, '2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, '10':10, 'jack':11, 'queen':12, 'king':13}

    def __init__(self, suit, rank, id):
        self.suit = suit
        self.rank = rank
        self.value = Card.rank_values[rank]
        self.order = Card.rank_order[rank]
        self.id = id

    def __str__(self):
        return f"{self.rank}_of_{self.suit}"

# Deck class
class Deck:
    def __init__(self):
        self.cards = []
        card_id = 0
        for suit in Card.suits:
            for rank in Card.ranks:
                card = Card(suit, rank, card_id)
                self.cards.append(card)
                card_id += 1

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self):
        if len(self.cards) > 0:
            return self.cards.pop()
        else:
            return None

# Minimum deadwood calculation with memoization
def min_deadwood(hand_ids, memo):
    if not hand_ids:
        return 0
    hand_tuple = frozenset(hand_ids)
    if hand_tuple in memo:
        return memo[hand_tuple]
    min_dead = sum(card_values[card_id] for card_id in hand_ids)

    # Try forming sets
    rank_groups = {}
    for card_id in hand_ids:
        rank = card_ranks[card_id]
        if rank not in rank_groups:
            rank_groups[rank] = []
        rank_groups[rank].append(card_id)
    for rank, group in rank_groups.items():
        if len(group) >= 3:
            for k in [3, 4]:
                if len(group) >= k:
                    set_ids = group[:k]
                    remaining = hand_ids - set(set_ids)
                    dead = min_deadwood(remaining, memo)
                    min_dead = min(min_dead, dead)

    # Try forming runs
    suit_groups = {}
    for card_id in hand_ids:
        suit = card_suits[card_id]
        if suit not in suit_groups:
            suit_groups[suit] = []
        suit_groups[suit].append(card_id)
    for suit, group in suit_groups.items():
        if len(group) >= 3:
            sorted_orders = sorted([card_orders[card_id] for card_id in group])
            for i in range(len(sorted_orders)):
                for j in range(i + 2, len(sorted_orders) + 1):
                    if sorted_orders[j - 1] - sorted_orders[i] == j - i - 1:
                        run_orders = sorted_orders[i:j]
                        if len(run_orders) >= 3:
                            run_ids = [card_id for card_id in group if card_orders[card_id] in run_orders]
                            remaining = hand_ids - set(run_ids)
                            dead = min_deadwood(remaining, memo)
                            min_dead = min(min_dead, dead)
    memo[hand_tuple] = min_dead
    return min_dead

# Pygame setup
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
BACKGROUND_COLOR = (0, 128, 0)


# Positions
stock_pos = (50, 50)
discard_pos = (150, 50)
player_hand_x = 50
player_hand_y = 400
ai_hand_x = 50
ai_hand_y = 50
card_width = 70
card_height = 100

# Load card images (assuming images are named like 'AH.png', '2H.png', etc.)
card_images = {}
for suit in Card.suits:
    for rank in Card.ranks:
        card_str = f"{rank}_of_{suit}"
        card_images[card_str] = pygame.image.load(f"cards/{card_str}.png")
        # scale image
        #card_images[card_str] = pygame.image.load(f"cards/{card_str}.png")
        card_images[card_str] = pygame.transform.smoothscale(pygame.image.load(f"cards/{card_str}.png"), (card_width, card_height)) 
#back_image = pygame.image.load("cards/back.png")
back_image = pygame.transform.smoothscale(pygame.image.load(f"cards/back.png"), (card_width, card_height))


# Game initialization
deck = Deck()
deck.shuffle()
player_hand = [deck.deal() for _ in range(10)]
ai_hand = [deck.deal() for _ in range(10)]
discard = [deck.deal()]
stock = deck.cards
turn = 0  # 0 for player, 1 for AI
game_state = 'drawing'
memo = {}

# Precompute card properties
card_values = [card.value for card in deck.cards]
card_ranks = [card.rank for card in deck.cards]
card_suits = [card.suit for card in deck.cards]
card_orders = [card.order for card in deck.cards]

running = True
while running:
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False
        elif event.type == MOUSEBUTTONDOWN and turn == 0:
            pos = pygame.mouse.get_pos()
            if game_state == 'drawing':
                stock_rect = back_image.get_rect(topleft=stock_pos)
                discard_rect = card_images[str(discard[-1])].get_rect(topleft=discard_pos) if discard else None
                if stock_rect.collidepoint(pos) and stock:
                    drawn_card = stock.pop()
                    player_hand.append(drawn_card)
                    game_state = 'discarding'
                elif discard_rect and discard_rect.collidepoint(pos) and discard:
                    drawn_card = discard.pop()
                    player_hand.append(drawn_card)
                    game_state = 'discarding'
            elif game_state == 'discarding':
                for i, card in enumerate(player_hand):
                    card_rect = card_images[str(card)].get_rect(topleft=(player_hand_x + i * card_width, player_hand_y))
                    if card_rect.collidepoint(pos):
                        discarded_card = player_hand.pop(i)
                        discard.append(discarded_card)
                        hand_ids = set(card.id for card in player_hand)
                        if min_deadwood(hand_ids, memo) == 0:
                            print("Player goes gin!")
                            running = False
                        else:
                            turn = 1
                        break

    if turn == 1:
        # AI's turn
        if stock:
            drawn_card = stock.pop()
            ai_hand.append(drawn_card)
        else:
            print("Stock empty")
            running = False
            continue
        # Choose card to discard
        min_dead = float('inf')
        best_card = None
        for card in ai_hand:
            temp_hand = [c for c in ai_hand if c != card]
            hand_ids = set(c.id for c in temp_hand)
            deadwood = min_deadwood(hand_ids, memo)
            if deadwood < min_dead:
                min_dead = deadwood
                best_card = card
        ai_hand.remove(best_card)
        discard.append(best_card)
        if min_dead == 0:
            print("AI goes gin!")
            running = False
        else:
            turn = 0

    # Draw everything
    screen.fill(BACKGROUND_COLOR)
    if stock:
        screen.blit(back_image, stock_pos)
    if discard:
        screen.blit(card_images[str(discard[-1])], discard_pos)
    sorted_player_hand = sorted(player_hand, key=lambda c: (Card.suits.index(c.suit), c.order))
    for i, card in enumerate(sorted_player_hand):
        screen.blit(card_images[str(card)], (player_hand_x + i * card_width, player_hand_y))
    for i in range(len(ai_hand)):
        screen.blit(back_image, (ai_hand_x + i * card_width, ai_hand_y))
    pygame.display.flip()

pygame.quit()