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

# Initialize global card property dictionaries
def initialize_card_props(deck):
    card_values = {}
    card_ranks = {}
    card_suits = {}
    card_orders = {}
    
    for card in deck.cards:
        card_values[card.id] = card.value
        card_ranks[card.id] = card.rank
        card_suits[card.id] = card.suit
        card_orders[card.id] = card.order
    
    return card_values, card_ranks, card_suits, card_orders

# Find melds (sets and runs) in a hand
def find_melds(hand_ids, card_ranks, card_suits, card_orders):
    melds = []
    
    # Find sets (3 or 4 cards of the same rank)
    rank_groups = {}
    for card_id in hand_ids:
        rank = card_ranks[card_id]
        if rank not in rank_groups:
            rank_groups[rank] = []
        rank_groups[rank].append(card_id)
    
    for rank, group in rank_groups.items():
        if len(group) >= 3:
            melds.append(("set", rank, group))
    
    # Find runs (3+ consecutive cards of the same suit)
    suit_groups = {}
    for card_id in hand_ids:
        suit = card_suits[card_id]
        if suit not in suit_groups:
            suit_groups[suit] = []
        suit_groups[suit].append(card_id)
    
    for suit, group in suit_groups.items():
        if len(group) >= 3:
            # Sort cards by their order within the suit
            sorted_group = sorted(group, key=lambda card_id: card_orders[card_id])
            
            # Find all possible runs (consecutive cards)
            runs = []
            current_run = []
            for i, card_id in enumerate(sorted_group):
                if not current_run or card_orders[card_id] == card_orders[current_run[-1]] + 1:
                    current_run.append(card_id)
                else:
                    if len(current_run) >= 3:
                        runs.append(current_run.copy())
                    current_run = [card_id]
                    
            if len(current_run) >= 3:
                runs.append(current_run)
                
            for run in runs:
                start_rank = card_ranks[run[0]]
                end_rank = card_ranks[run[-1]]
                melds.append(("run", f"{start_rank}-{end_rank} of {suit}", run))
    
    return melds

# Minimum deadwood calculation with memoization
def min_deadwood(hand_ids, memo, card_values, card_ranks, card_suits, card_orders, debug_info=None):
    if not hand_ids:
        return 0
    
    hand_tuple = frozenset(hand_ids)
    if hand_tuple in memo:
        return memo[hand_tuple]
    
    # Start with all cards as deadwood
    min_dead = sum(card_values[card_id] for card_id in hand_ids)
    best_melds = []
    
    # Find all possible melds
    all_melds = find_melds(hand_ids, card_ranks, card_suits, card_orders)
    
    # If no melds, return sum of card values
    if not all_melds:
        if debug_info is not None:
            debug_info['melds'] = []
            debug_info['deadwood'] = list(hand_ids)
            debug_info['deadwood_value'] = min_dead
        memo[hand_tuple] = min_dead
        return min_dead
    
    # Try each meld and recursively find minimum deadwood
    for meld_type, meld_name, meld_cards in all_melds:
        remaining = hand_ids - set(meld_cards)
        remaining_debug = {} if debug_info is not None else None
        dead = min_deadwood(remaining, memo, card_values, card_ranks, card_suits, card_orders, remaining_debug)
        
        if dead < min_dead:
            min_dead = dead
            if debug_info is not None:
                best_melds = [(meld_type, meld_name, meld_cards)]
                if 'melds' in remaining_debug:
                    best_melds.extend(remaining_debug['melds'])
                debug_info['melds'] = best_melds
                debug_info['deadwood'] = remaining_debug.get('deadwood', []) if dead > 0 else []
                debug_info['deadwood_value'] = dead
    
    memo[hand_tuple] = min_dead
    return min_dead

# Helper function to get combinations
def get_combinations(items, k):
    if k == 0 or not items:
        return [[]]
    if len(items) == k:
        return [items]
    
    first, rest = items[0], items[1:]
    with_first = [[first] + combo for combo in get_combinations(rest, k-1)]
    without_first = get_combinations(rest, k)
    return with_first + without_first

# Debug panel class
class DebugPanel:
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.color = (50, 50, 50, 180)  # Semi-transparent dark gray
        self.border_color = (200, 200, 200)
        self.text_color = (255, 255, 255)
        self.font = pygame.font.SysFont('Arial', 16)
        self.title_font = pygame.font.SysFont('Arial', 18, bold=True)
        self.info = {}
        self.visible = True
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        
    def toggle_visibility(self):
        self.visible = not self.visible
        
    def update_info(self, info):
        self.info = info
        
    def draw(self, surface):
        if not self.visible:
            return
            
        # Clear the surface
        self.surface.fill((0, 0, 0, 0))
        
        # Draw background
        pygame.draw.rect(self.surface, self.color, (0, 0, self.rect.width, self.rect.height))
        pygame.draw.rect(self.surface, self.border_color, (0, 0, self.rect.width, self.rect.height), 2)
        
        # Draw title
        title = self.title_font.render("Debug Information", True, self.text_color)
        self.surface.blit(title, (10, 10))
        
        y = 40
        line_height = 20
        
        # Draw player info
        if 'player' in self.info:
            player_title = self.font.render("Player Analysis:", True, (255, 220, 100))
            self.surface.blit(player_title, (10, y))
            y += line_height
            
            player_info = self.info['player']
            if 'deadwood_value' in player_info:
                deadwood_text = self.font.render(f"Deadwood: {player_info['deadwood_value']} points", True, self.text_color)
                self.surface.blit(deadwood_text, (20, y))
                y += line_height
            
            if 'melds' in player_info:
                melds_text = self.font.render(f"Melds found: {len(player_info['melds'])}", True, self.text_color)
                self.surface.blit(melds_text, (20, y))
                y += line_height
                
                for i, (meld_type, meld_name, _) in enumerate(player_info['melds']):
                    meld_text = self.font.render(f"- {meld_type.capitalize()}: {meld_name}", True, self.text_color)
                    self.surface.blit(meld_text, (30, y))
                    y += line_height
                    
                    if i >= 2:  # Limit display to prevent overflow
                        if len(player_info['melds']) > 3:
                            more_text = self.font.render(f"...and {len(player_info['melds']) - 3} more", True, self.text_color)
                            self.surface.blit(more_text, (30, y))
                            y += line_height
                        break
        
        y += line_height // 2
        
        # Draw AI info
        if 'ai' in self.info:
            ai_title = self.font.render("AI Analysis:", True, (100, 220, 255))
            self.surface.blit(ai_title, (10, y))
            y += line_height
            
            ai_info = self.info['ai']
            if 'decision' in ai_info:
                decision_text = self.font.render(f"Last move: {ai_info['decision']}", True, self.text_color)
                self.surface.blit(decision_text, (20, y))
                y += line_height
            
            if 'deadwood_value' in ai_info:
                deadwood_text = self.font.render(f"Deadwood: {ai_info['deadwood_value']} points", True, self.text_color)
                self.surface.blit(deadwood_text, (20, y))
                y += line_height
            
            if 'discard_options' in ai_info:
                options = ai_info['discard_options']
                options_text = self.font.render(f"Top discard options:", True, self.text_color)
                self.surface.blit(options_text, (20, y))
                y += line_height
                
                for i, (card_str, deadwood) in enumerate(options):
                    if i >= 3:  # Show only top 3 options
                        break
                    option_text = self.font.render(f"- {card_str}: {deadwood} deadwood", True, self.text_color)
                    self.surface.blit(option_text, (30, y))
                    y += line_height
        
        # Draw help text
        help_text = self.font.render("Press D to toggle debug panel", True, (180, 180, 180))
        self.surface.blit(help_text, (10, self.rect.height - 30))
        
        # Blit the surface to the main surface
        surface.blit(self.surface, self.rect)

# Pygame setup
pygame.init()
WIDTH, HEIGHT = 1000, 700  # Increased window size to accommodate debug panel
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Gin Rummy with Debug")
BACKGROUND_COLOR = (0, 90, 0)  # Slightly lighter green
font = pygame.font.SysFont('Arial', 20)

# Positions
stock_pos = (50, 50)
discard_pos = (150, 50)
player_hand_x = 50
player_hand_y = 500
ai_hand_x = 50
ai_hand_y = 150
card_width = 70
card_height = 100
card_spacing = 35  # Adjust for overlap

# Create debug panel
debug_panel = DebugPanel(WIDTH - 300, 50, 280, HEIGHT - 100)

# Load card images
card_images = {}
try:
    for suit in Card.suits:
        for rank in Card.ranks:
            card_str = f"{rank}_of_{suit}"
            image_path = f"cards/{card_str}.png"
            try:
                card_images[card_str] = pygame.transform.smoothscale(
                    pygame.image.load(image_path), (card_width, card_height)
                )
            except pygame.error:
                print(f"Warning: Could not load image {image_path}")
                # Create a placeholder card
                placeholder = pygame.Surface((card_width, card_height))
                placeholder.fill((255, 255, 255))
                pygame.draw.rect(placeholder, (0, 0, 0), placeholder.get_rect(), 2)
                text = font.render(card_str[:7] + "...", True, (0, 0, 0)) if len(card_str) > 7 else font.render(card_str, True, (0, 0, 0))
                placeholder.blit(text, (5, 40))
                card_images[card_str] = placeholder

    back_image = pygame.transform.smoothscale(pygame.image.load("cards/back.png"), (card_width, card_height))
except pygame.error:
    print("Warning: Could not load card back image")
    # Create a placeholder for card back
    back_image = pygame.Surface((card_width, card_height))
    back_image.fill((0, 0, 255))
    pygame.draw.rect(back_image, (255, 255, 255), back_image.get_rect(), 2)

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
card_values, card_ranks, card_suits, card_orders = initialize_card_props(deck)

# Debug information
debug_info = {
    'player': {},
    'ai': {'decision': 'Game started', 'discard_options': []}
}

# Initial analysis
player_ids = {card.id for card in player_hand}
player_debug = {}
player_deadwood = min_deadwood(player_ids, memo, card_values, card_ranks, card_suits, card_orders, player_debug)
debug_info['player'] = player_debug
debug_info['player']['deadwood_value'] = player_deadwood

ai_ids = {card.id for card in ai_hand}
ai_debug = {}
ai_deadwood = min_deadwood(ai_ids, memo, card_values, card_ranks, card_suits, card_orders, ai_debug)
debug_info['ai'] = ai_debug
debug_info['ai']['deadwood_value'] = ai_deadwood
debug_info['ai']['decision'] = 'Game started'
debug_info['ai']['discard_options'] = []

debug_panel.update_info(debug_info)

# Game loop
running = True
message = "Your turn: Draw from stock or discard pile"
clock = pygame.time.Clock()

while running:
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False
        elif event.type == KEYDOWN:
            if event.key == K_d:  # Toggle debug panel
                debug_panel.toggle_visibility()
        elif event.type == MOUSEBUTTONDOWN and turn == 0:
            pos = pygame.mouse.get_pos()
            if game_state == 'drawing':
                stock_rect = back_image.get_rect(topleft=stock_pos)
                discard_rect = card_images[str(discard[-1])].get_rect(topleft=discard_pos) if discard else None
                
                if stock_rect.collidepoint(pos) and stock:
                    drawn_card = stock.pop()
                    player_hand.append(drawn_card)
                    game_state = 'discarding'
                    message = "Your turn: Select a card to discard"
                elif discard_rect and discard_rect.collidepoint(pos) and discard:
                    drawn_card = discard.pop()
                    player_hand.append(drawn_card)
                    game_state = 'discarding'
                    message = "Your turn: Select a card to discard"
            
            elif game_state == 'discarding':
                for i, card in enumerate(player_hand):
                    card_rect = card_images[str(card)].get_rect(topleft=(player_hand_x + i * card_spacing, player_hand_y))
                    if card_rect.collidepoint(pos):
                        discarded_card = player_hand.pop(i)
                        discard.append(discarded_card)
                        
                        # Update player analysis after discard
                        player_ids = {card.id for card in player_hand}
                        player_debug = {}
                        player_deadwood = min_deadwood(player_ids, memo, card_values, card_ranks, card_suits, card_orders, player_debug)
                        debug_info['player'] = player_debug
                        debug_info['player']['deadwood_value'] = player_deadwood
                        debug_panel.update_info(debug_info)
                        
                        if player_deadwood == 0:
                            message = "Player goes gin! You win!"
                            print("Player goes gin!")
                        else:
                            message = f"AI's turn (Your deadwood: {player_deadwood})"
                            turn = 1
                        game_state = 'drawing'
                        break

    if turn == 1 and running:
        # AI's turn
        message = "AI is thinking..."
        
        # Draw screen first to show "AI is thinking"
        screen.fill(BACKGROUND_COLOR)
        message_text = font.render(message, True, (255, 255, 255))
        screen.blit(message_text, (WIDTH//2 - message_text.get_width()//2, HEIGHT//2))
        debug_panel.draw(screen)
        pygame.display.flip()
        
        # AI draws a card
        if stock:
            drawn_card = stock.pop()
            ai_hand.append(drawn_card)
            debug_info['ai']['decision'] = f"Drew {drawn_card} from stock"
        else:
            message = "Stock empty. Game over!"
            running = False
            continue
            
        # Choose card to discard - with debug info
        min_dead = float('inf')
        best_card = None
        discard_options = []
        
        for card in ai_hand:
            temp_hand = [c for c in ai_hand if c != card]
            hand_ids = {c.id for c in temp_hand}
            card_debug = {}
            deadwood = min_deadwood(hand_ids, memo, card_values, card_ranks, card_suits, card_orders, card_debug)
            
            discard_options.append((str(card), deadwood))
            
            if deadwood < min_dead:
                min_dead = deadwood
                best_card = card
                ai_debug = card_debug
        
        # Sort discard options by deadwood (best first)
        discard_options.sort(key=lambda x: x[1])
        debug_info['ai']['discard_options'] = discard_options[:5]  # Top 5 options
        
        # Discard
        ai_hand.remove(best_card)
        discard.append(best_card)
        debug_info['ai']['decision'] += f", discarded {best_card} ({min_dead} deadwood)"
        
        # Update AI analysis
        debug_info['ai'] = ai_debug
        debug_info['ai']['deadwood_value'] = min_dead
        debug_panel.update_info(debug_info)
        
        if min_dead == 0:
            message = "AI goes gin! You lose!"
            print("AI goes gin!")
        else:
            message = f"Your turn (AI deadwood: {min_dead})"
            turn = 0
            game_state = 'drawing'

    # Draw everything
    screen.fill(BACKGROUND_COLOR)
    
    # Draw stock and discard piles
    if stock:
        screen.blit(back_image, stock_pos)
        stock_count = font.render(f"Stock: {len(stock)}", True, (255, 255, 255))
        screen.blit(stock_count, (stock_pos[0], stock_pos[1] - 25))
    
    if discard:
        screen.blit(card_images[str(discard[-1])], discard_pos)
        discard_label = font.render("Discard", True, (255, 255, 255))
        screen.blit(discard_label, (discard_pos[0], discard_pos[1] - 25))
    
    # Draw player's hand
    player_label = font.render("Your Hand:", True, (255, 255, 255))
    screen.blit(player_label, (player_hand_x, player_hand_y - 25))
    
    sorted_player_hand = sorted(player_hand, key=lambda c: (Card.suits.index(c.suit), c.order))
    for i, card in enumerate(sorted_player_hand):
        screen.blit(card_images[str(card)], (player_hand_x + i * card_spacing, player_hand_y))
    
    # Draw AI's hand (face down)
    ai_label = font.render("AI Hand:", True, (255, 255, 255))
    screen.blit(ai_label, (ai_hand_x, ai_hand_y - 25))
    
    for i in range(len(ai_hand)):
        screen.blit(back_image, (ai_hand_x + i * card_spacing, ai_hand_y))
    
    # Draw message
    message_text = font.render(message, True, (255, 255, 255))
    screen.blit(message_text, (WIDTH//2 - message_text.get_width()//2, HEIGHT//2))
    
    # Draw debug panel
    debug_panel.draw(screen)
    
    pygame.display.flip()
    clock.tick(30)  # Cap at 30 FPS

pygame.quit()