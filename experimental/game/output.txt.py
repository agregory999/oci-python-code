Below is a complete Pygame application to play Gin Rummy, designed for a single player against an AI opponent. This implementation includes card management, basic game logic for drawing and discarding, and a simplified win condition where the game ends when a player "goes gin" (forms all cards into sets or runs with no deadwood). The AI uses a simple strategy to minimize its deadwood.

---

### Code

```python
import pygame
import random
from pygame.locals import *

# Card class to represent individual cards
class Card:
    suits = ['H', 'D', 'C', 'S']  # Hearts, Diamonds, Clubs, Spades
    ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    rank_values = {'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10}
    rank_order = {'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13}

    def __init__(self, suit, rank, id):
        self.suit = suit
        self.rank = rank
        self.value = self.rank_values[rank]  # For scoring
        self.order = self.rank_order[rank]   # For runs
        self.id = id  # Unique identifier

    def __str__(self):
        return f"{self.rank}{self.suit}"

# Deck class to manage the card deck
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
        return self.cards.pop() if self.cards else None

# Function to calculate minimum deadwood with memoization
def min_deadwood(hand_ids, memo, card_values, card_ranks, card_suits, card_orders):
    if not hand_ids:
        return 0
    hand_tuple = frozenset(hand_ids)
    if hand_tuple in memo:
        return memo[hand_tuple]
    
    # Initial deadwood is the sum of all card values
    min_dead = sum(card_values[card_id] for card_id in hand_ids)

    # Try forming sets (3 or 4 cards of same rank)
    rank_groups = {}
    for card_id in hand_ids:
        rank = card_ranks[card_id]
        rank_groups.setdefault(rank, []).append(card_id)
    for group in rank_groups.values():
        if len(group) >= 3:
            for k in [3, 4]:
                if len(group) >= k:
                    set_ids = group[:k]
                    remaining = hand_ids - set(set_ids)
                    dead = min_deadwood(remaining, memo, card_values, card_ranks, card_suits, card_orders)
                    min_dead = min(min_dead, dead)

    # Try forming runs (3+ consecutive cards of same suit)
    suit_groups = {}
    for card_id in hand_ids:
        suit = card_suits[card_id]
        suit_groups.setdefault(suit, []).append(card_id)
    for group in suit_groups.values():
        if len(group) >= 3:
            sorted_orders = sorted([card_orders[card_id] for card_id in group])
            for i in range(len(sorted_orders)):
                for j in range(i + 2, len(sorted_orders) + 1):
                    if sorted_orders[j - 1] - sorted_orders[i] == j - i - 1:
                        run_orders = sorted_orders[i:j]
                        run_ids = {card_id for card_id in group if card_orders[card_id] in run_orders}
                        remaining = hand_ids - run_ids
                        dead = min_deadwood(remaining, memo, card_values, card_ranks, card_suits, card_orders)
                        min_dead = min(min_dead, dead)
    
    memo[hand_tuple] = min_dead
    return min_dead

# Pygame setup
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Gin Rummy")
BACKGROUND_COLOR = (0, 128, 0)  # Green table

# Load card images (placeholder - replace with actual image loading)
# Assume images are in a 'cards' folder, named like 'AH.png', '2H.png', etc.
card_images = {}
try:
    for suit in Card.suits:
        for rank in Card.ranks:
            card_str = f"{rank}{suit}"
            card_images[card_str] = pygame.image.load(f"cards/{card_str}.png").convert_alpha()
    back_image = pygame.image.load("cards/back.png").convert_alpha()
except FileNotFoundError:
    # Fallback to text-based cards if images are missing
    card_images = {f"{rank}{suit}": pygame.Surface((70, 100)) for suit in Card.suits for rank in Card.ranks}
    back_image = pygame.Surface((70, 100))
    font = pygame.font.SysFont(None, 36)
    for card_str, surface in card_images.items():
        surface.fill((255, 255, 255))
        text = font.render(card_str, True, (0, 0, 0))
        surface.blit(text, (10, 40))
    back_image.fill((0, 0, 255))

# Game positions
CARD_WIDTH, CARD_HEIGHT = 70, 100
STOCK_POS = (50, 50)
DISCARD_POS = (150, 50)
PLAYER_HAND_X, PLAYER_HAND_Y = 50, 400
AI_HAND_X, AI_HAND_Y = 50, 150

# Initialize game state
deck = Deck()
deck.shuffle()
player_hand = [deck.deal() for _ in range(10)]
ai_hand = [deck.deal() for _ in range(10)]
discard = [deck.deal()]
stock = deck.cards
turn = 0  # 0 for player, 1 for AI
game_state = 'drawing'
memo = {}
running = True
clock = pygame.time.Clock()

# Precompute card properties for efficiency
card_values = [card.value for card in deck.cards] + [0] * 52  # Pad for safety
card_ranks = [card.rank for card in deck.cards] + [''] * 52
card_suits = [card.suit for card in deck.cards] + [''] * 52
card_orders = [card.order for card in deck.cards] + [0] * 52

# Main game loop
while running:
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False
        elif event.type == MOUSEBUTTONDOWN and turn == 0:
            pos = pygame.mouse.get_pos()
            if game_state == 'drawing':
                stock_rect = back_image.get_rect(topleft=STOCK_POS)
                discard_rect = card_images[str(discard[-1])].get_rect(topleft=DISCARD_POS) if discard else None
                if stock_rect.collidepoint(pos) and stock:
                    player_hand.append(stock.pop())
                    game_state = 'discarding'
                elif discard_rect and discard_rect.collidepoint(pos) and discard:
                    player_hand.append(discard.pop())
                    game_state = 'discarding'
            elif game_state == 'discarding':
                for i, card in enumerate(player_hand):
                    card_rect = pygame.Rect(PLAYER_HAND_X + i * CARD_WIDTH, PLAYER_HAND_Y, CARD_WIDTH, CARD_HEIGHT)
                    if card_rect.collidepoint(pos):
                        discard.append(player_hand.pop(i))
                        hand_ids = {card.id for card in player_hand}
                        if min_deadwood(hand_ids, memo, card_values, card_ranks, card_suits, card_orders) == 0:
                            score = sum(card.value for card in ai_hand)
                            print(f"Player goes gin! Score: {score}")
                            running = False
                        else:
                            turn = 1
                        break

    # AI's turn
    if turn == 1:
        pygame.time.wait(500)  # Simulate AI thinking
        if stock:
            ai_hand.append(stock.pop())
        else:
            print("Stock empty - game ends")
            running = False
            continue
        # Choose card to discard that minimizes deadwood
        min_dead = float('inf')
        best_card = None
        for card in ai_hand:
            temp_hand = [c for c in ai_hand if c != card]
            hand_ids = {c.id for c in temp_hand}
            deadwood = min_deadwood(hand_ids, memo, card_values, card_ranks, card_suits, card_orders)
            if deadwood < min_dead:
                min_dead = deadwood
                best_card = card
        ai_hand.remove(best_card)
        discard.append(best_card)
        if min_dead == 0:
            score = sum(card.value for card in player_hand)
            print(f"AI goes gin! Score: {score}")
            running = False
        else:
            turn = 0

    # Draw the game
    screen.fill(BACKGROUND_COLOR)
    if stock:
        screen.blit(back_image, STOCK_POS)
    if discard:
        screen.blit(card_images[str(discard[-1])], DISCARD_POS)
    sorted_player_hand = sorted(player_hand, key=lambda c: (Card.suits.index(c.suit), c.order))
    for i, card in enumerate(sorted_player_hand):
        screen.blit(card_images[str(card)], (PLAYER_HAND_X + i * CARD_WIDTH, PLAYER_HAND_Y))
    for i in range(len(ai_hand)):
        screen.blit(back_image, (AI_HAND_X + i * CARD_WIDTH, AI_HAND_Y))
    
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
```

---

### Explanation

#### **Card and Deck Classes**
- **Card**: Represents a single card with `suit`, `rank`, `value` (for scoring), `order` (for runs), and a unique `id`. Suits are 'H', 'D', 'C', 'S', and ranks range from 'A' to 'K'.
- **Deck**: Creates a standard 52-card deck, assigns unique IDs (0-51), and provides methods to shuffle and deal cards.

#### **Game Logic**
- **min_deadwood**: A memoized recursive function that calculates the minimum points of unmatched cards (deadwood) in a hand. It tries forming:
  - **Sets**: 3 or 4 cards of the same rank.
  - **Runs**: 3 or more consecutive cards of the same suit (e.g., 2H-3H-4H).
  - Uses card IDs for memoization with `frozenset` to optimize performance for hands of up to 11 cards.

- **Win Condition**: The game ends when a player "goes gin," meaning their deadwood is 0 (all cards are in sets or runs). The score is the sum of the opponent's card values (simplified from full Gin Rummy rules, which include a 25-point bonus).

#### **User Interface**
- **Display**: 
  - Stock pile at top-left (facedown).
  - Discard pile next to it (top card face-up).
  - Player's hand at the bottom (sorted by suit and rank).
  - AI's hand in the middle (facedown).
- **Interaction**: 
  - Click stock or discard to draw during the player's turn.
  - Click a card in the hand to discard it.

#### **AI Opponent**
- Draws from the stock each turn.
- Discards the card that, when removed, results in the lowest deadwood value for the remaining 10 cards.
- Checks for gin after discarding.

#### **Game Flow**
1. **Setup**: Deal 10 cards to each player, place one card in the discard pile, and the rest in the stock.
2. **Player Turn**: Draw from stock or discard, then discard a card. If deadwood = 0, the player wins.
3. **AI Turn**: Draw from stock, discard to minimize deadwood. If deadwood = 0, the AI wins.
4. **End**: Game stops when a player goes gin or stock runs out (ends in a draw for simplicity).

---

### Prerequisites
- **Pygame**: Install via `pip install pygame`.
- **Card Images**: Place 52 card images (e.g., `AH.png`, `2H.png`) and a `back.png` in a `cards` folder. If images are missing, the code falls back to text-based cards.

---

### Simplifications
- Only implements "going gin" (no knocking with deadwood ≤ 10).
- Scoring is the opponent's total card values (no gin bonus or layoff).
- Single hand game (no multi-hand scoring to 100 points).
- Basic AI strategy without advanced heuristics.

This app provides a functional Gin Rummy experience with Pygame, focusing on core gameplay mechanics. You can enhance it by adding knocking, better AI, animations, or a graphical win screen.