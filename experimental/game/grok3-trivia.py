# write a game in python using pygame that asks trivia questions sourced from wikipedia.   Questions should be medium difficulty and by category that the user can select.  Keep score and play a fun sound when the player gets enough correct to win.

# Solution 1

# import asyncio
# import platform
# import pygame
# import random
# import numpy as np

# # Initialize Pygame
# pygame.init()

# # Set up the display
# WIDTH, HEIGHT = 800, 600
# screen = pygame.display.set_mode((WIDTH, HEIGHT))
# pygame.display.set_caption("Trivia Game")

# # Colors
# WHITE = (255, 255, 255)
# BLACK = (0, 0, 0)
# GREEN = (0, 255, 0)
# RED = (255, 0, 0)

# # Font
# font = pygame.font.Font(None, 36)

# # Hardcoded trivia questions (simulating Wikipedia-sourced content)
# TRIVIA_DATA = {
#     "History": [
#         {"question": "Who was the first President of the United States?", "correct": "George Washington", "incorrect": ["Thomas Jefferson", "Abraham Lincoln", "John Adams"]},
#         {"question": "In which year did World War II end?", "correct": "1945", "incorrect": ["1939", "1941", "1950"]},
#     ],
#     "Science": [
#         {"question": "What gas do plants primarily use for photosynthesis?", "correct": "Carbon Dioxide", "incorrect": ["Oxygen", "Nitrogen", "Hydrogen"]},
#         {"question": "What is the chemical symbol for gold?", "correct": "Au", "incorrect": ["Ag", "Fe", "Cu"]},
#     ],
#     "Geography": [
#         {"question": "What is the capital of Brazil?", "correct": "Brasilia", "incorrect": ["Rio de Janeiro", "Sao Paulo", "Salvador"]},
#         {"question": "Which continent is the Sahara Desert located on?", "correct": "Africa", "incorrect": ["Asia", "Australia", "South America"]},
#     ]
# }

# CATEGORIES = list(TRIVIA_DATA.keys())
# FPS = 60

# # Game state variables
# state = "category_selection"
# selected_category = None
# questions = []
# current_question_index = 0
# score = 0
# feedback = ""
# feedback_color = BLACK
# options = []
# option_rects = []

# # Generate a simple win sound using NumPy (since no file I/O)
# sample_rate = 44100
# freq = 440  # A4 note
# duration = 1  # 1 second
# t = np.linspace(0, duration, int(sample_rate * duration), False)
# sound_wave = 0.5 * np.sin(2 * np.pi * freq * t)
# stereo_sound = np.array([sound_wave, sound_wave]).T  # 2D array for stereo
# win_sound = pygame.sndarray.make_sound((stereo_sound * 32767).astype(np.int16))

# def setup():
#     global state, selected_category, questions, current_question_index, score, feedback, options, option_rects
#     state = "category_selection"
#     selected_category = None
#     questions = []
#     current_question_index = 0
#     score = 0
#     feedback = ""
#     options = []
#     option_rects = []

# def display_text(text, x, y, color=BLACK):
#     rendered_text = font.render(text, True, color)
#     screen.blit(rendered_text, (x, y))

# def update_loop():
#     global state, selected_category, questions, current_question_index, score, feedback, feedback_color, options, option_rects

#     screen.fill(WHITE)

#     if state == "category_selection":
#         display_text("Select a category:", 100, 100)
#         category_rects = []
#         y = 150
#         for category in CATEGORIES:
#             text = font.render(category, True, BLACK)
#             rect = text.get_rect(topleft=(100, y))
#             screen.blit(text, rect)
#             category_rects.append((rect, category))
#             y += 50

#         for event in pygame.event.get():
#             if event.type == pygame.QUIT:
#                 pygame.quit()
#                 return
#             elif event.type == pygame.MOUSEBUTTONDOWN:
#                 pos = pygame.mouse.get_pos()
#                 for rect, category in category_rects:
#                     if rect.collidepoint(pos):
#                         selected_category = category
#                         questions = TRIVIA_DATA[category][:10]  # Limit to 10 questions
#                         random.shuffle(questions)
#                         state = "question"
#                         break

#     elif state == "question":
#         if current_question_index < len(questions):
#             question = questions[current_question_index]
#             if not options:
#                 options = question["incorrect"] + [question["correct"]]
#                 random.shuffle(options)
#                 option_rects = []

#             display_text(f"Question {current_question_index + 1}/{len(questions)}", 100, 50)
#             display_text(question["question"], 100, 100)
#             for i, option in enumerate(options):
#                 text = font.render(f"{chr(65 + i)}. {option}", True, BLACK)
#                 rect = text.get_rect(topleft=(100, 150 + i * 50))
#                 screen.blit(text, rect)
#                 if i >= len(option_rects):
#                     option_rects.append(rect)
#             display_text(f"Score: {score}", 600, 50)
#             if feedback:
#                 display_text(feedback, 100, 500, feedback_color)

#             for event in pygame.event.get():
#                 if event.type == pygame.QUIT:
#                     pygame.quit()
#                     return
#                 elif event.type == pygame.MOUSEBUTTONDOWN and not feedback:
#                     pos = pygame.mouse.get_pos()
#                     for i, rect in enumerate(option_rects):
#                         if rect.collidepoint(pos):
#                             if options[i] == question["correct"]:
#                                 score += 1
#                                 feedback = "Correct!"
#                                 feedback_color = GREEN
#                             else:
#                                 feedback = f"Incorrect. Correct answer: {question['correct']}"
#                                 feedback_color = RED
#                             break
#                 elif event.type == pygame.MOUSEBUTTONDOWN and feedback:
#                     current_question_index += 1
#                     feedback = ""
#                     options = []
#                     option_rects = []

#         else:
#             state = "result"

#     elif state == "result":
#         display_text(f"Final Score: {score}/{len(questions)}", 100, 100)
#         if score >= 7:
#             display_text("Congratulations! You win!", 100, 150, GREEN)
#             win_sound.play()
#         else:
#             display_text("Better luck next time!", 100, 150, RED)
        
#         play_again_rect = font.render("Play Again", True, BLACK).get_rect(topleft=(100, 250))
#         exit_rect = font.render("Exit", True, BLACK).get_rect(topleft=(100, 300))
#         screen.blit(font.render("Play Again", True, BLACK), play_again_rect)
#         screen.blit(font.render("Exit", True, BLACK), exit_rect)

#         for event in pygame.event.get():
#             if event.type == pygame.QUIT:
#                 pygame.quit()
#                 return
#             elif event.type == pygame.MOUSEBUTTONDOWN:
#                 pos = pygame.mouse.get_pos()
#                 if play_again_rect.collidepoint(pos):
#                     setup()
#                 elif exit_rect.collidepoint(pos):
#                     pygame.quit()
#                     return

#     pygame.display.flip()

# async def main():
#     setup()
#     while True:
#         update_loop()
#         await asyncio.sleep(1.0 / FPS)

# if platform.system() == "Emscripten":
#     asyncio.ensure_future(main())
# else:
#     if __name__ == "__main__":
#         asyncio.run(main())

# Sol 2

import pygame
import asyncio
import platform
import random
import numpy as np

# Sample trivia data (since network calls are limited in Pyodide)
TRIVIA_DATA = {
    "Science": [
        {"question": "What gas do plants primarily use for photosynthesis?", "answers": ["Carbon Dioxide", "Oxygen", "Nitrogen", "Hydrogen"], "correct": "Carbon Dioxide"},
        {"question": "What is the chemical symbol for gold?", "answers": ["Au", "Ag", "Fe", "Cu"], "correct": "Au"},
        {"question": "Which planet is known as the Red Planet?", "answers": ["Mars", "Jupiter", "Venus", "Saturn"], "correct": "Mars"},
        {"question": "What is the primary source of energy for Earth's climate system?", "answers": ["Sun", "Moon", "Earth's core", "Wind"], "correct": "Sun"},
        {"question": "What element has the atomic number 1?", "answers": ["Hydrogen", "Helium", "Lithium", "Beryllium"], "correct": "Hydrogen"},
        {"question": "What is the hardest naturally occurring substance known?", "answers": ["Diamond", "Quartz", "Topaz", "Ruby"], "correct": "Diamond"},
        {"question": "Which organ is responsible for pumping blood in humans?", "answers": ["Heart", "Lungs", "Liver", "Kidneys"], "correct": "Heart"},
        {"question": "What gas makes up most of Earth's atmosphere?", "answers": ["Nitrogen", "Oxygen", "Carbon Dioxide", "Argon"], "correct": "Nitrogen"},
        {"question": "What is the boiling point of water in Celsius?", "answers": ["100", "0", "50", "200"], "correct": "100"},
        {"question": "Which scientist proposed the theory of relativity?", "answers": ["Albert Einstein", "Isaac Newton", "Galileo Galilei", "Nikola Tesla"], "correct": "Albert Einstein"}
    ],
    "History": [
        {"question": "Who was the first President of the United States?", "answers": ["George Washington", "Thomas Jefferson", "Abraham Lincoln", "John Adams"], "correct": "George Washington"},
        {"question": "In which year did World War II end?", "answers": ["1945", "1939", "1941", "1950"], "correct": "1945"},
        {"question": "Which empire built the Colosseum?", "answers": ["Roman", "Greek", "Egyptian", "Persian"], "correct": "Roman"},
        {"question": "Who led the French Revolution?", "answers": ["Napoleon Bonaparte", "Louis XVI", "Robespierre", "Marie Antoinette"], "correct": "Robespierre"},
        {"question": "What was the name of the ship that sank in 1912?", "answers": ["Titanic", "Lusitania", "Britannic", "Iconic"], "correct": "Titanic"},
        {"question": "Which country was divided by the Berlin Wall?", "answers": ["Germany", "France", "Poland", "Austria"], "correct": "Germany"},
        {"question": "Who discovered America in 1492?", "answers": ["Christopher Columbus", "Leif Erikson", "Ferdinand Magellan", "Marco Polo"], "correct": "Christopher Columbus"},
        {"question": "In which century did the Renaissance begin?", "answers": ["14th", "12th", "16th", "18th"], "correct": "14th"},
        {"question": "Which war was fought between the North and South in the US?", "answers": ["Civil War", "Revolutionary War", "World War I", "Vietnam War"], "correct": "Civil War"},
        {"question": "Who was the first man to step on the moon?", "answers": ["Neil Armstrong", "Buzz Aldrin", "Yuri Gagarin", "Alan Shepard"], "correct": "Neil Armstrong"}
    ]
}

# Initialize Pygame
pygame.init()
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Trivia Game")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)

# Game states
STATE_CATEGORY, STATE_QUESTION, STATE_RESULT = 0, 1, 2

# Global variables
state = STATE_CATEGORY
categories = list(TRIVIA_DATA.keys())
selected_category = None
questions = []
current_question_idx = 0
score = 0

# Generate a simple winning sound (since file loading isn't possible)
sample_rate = 44100
duration = 0.5  # seconds
frequency = 440  # Hz (A4 note)
t = np.linspace(0, duration, int(sample_rate * duration), False)
sound_wave = 0.5 * np.sin(2 * np.pi * frequency * t)
sound_array = (sound_wave * 32767).astype(np.int16)
stereo_sound = np.column_stack((sound_array, sound_array))  # 2D for stereo
win_sound = pygame.sndarray.make_sound(stereo_sound)

def draw_text(text, x, y, color=(0, 0, 0)):
    text_surface = font.render(text, True, color)
    screen.blit(text_surface, (x, y))
    return text_surface.get_rect(topleft=(x, y))

def setup():
    global state, selected_category, questions, current_question_idx, score
    state = STATE_CATEGORY
    selected_category = None
    questions = []
    current_question_idx = 0
    score = 0

def update_loop():
    global state, selected_category, questions, current_question_idx, score
    screen.fill((255, 255, 255))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos
            if state == STATE_CATEGORY:
                for i, category in enumerate(categories):
                    rect = pygame.Rect(100, 100 + i * 50, 600, 40)
                    if rect.collidepoint(mouse_pos):
                        selected_category = category
                        questions = random.sample(TRIVIA_DATA[category], 10) if len(TRIVIA_DATA[category]) >= 10 else TRIVIA_DATA[category]
                        state = STATE_QUESTION
            elif state == STATE_QUESTION:
                question = questions[current_question_idx]
                for i, answer in enumerate(question["answers"]):
                    rect = pygame.Rect(100, 200 + i * 60, 600, 50)
                    if rect.collidepoint(mouse_pos):
                        if answer == question["correct"]:
                            score += 1
                        current_question_idx += 1
                        if current_question_idx >= len(questions):
                            state = STATE_RESULT
                        break
            elif state == STATE_RESULT:
                play_again_rect = pygame.Rect(300, 400, 200, 50)
                if play_again_rect.collidepoint(mouse_pos):
                    setup()

    if state == STATE_CATEGORY:
        draw_text("Select a Category:", 100, 50)
        for i, category in enumerate(categories):
            draw_text(category, 100, 100 + i * 50)
    elif state == STATE_QUESTION:
        question = questions[current_question_idx]
        draw_text(f"Score: {score} / {len(questions)}", 600, 50)
        draw_text(f"Question {current_question_idx + 1}: {question['question']}", 100, 100)
        for i, answer in enumerate(question["answers"]):
            rect = pygame.Rect(100, 200 + i * 60, 600, 50)
            pygame.draw.rect(screen, (200, 200, 200), rect)
            draw_text(answer, 100 + 10, 200 + i * 60 + 10)
    elif state == STATE_RESULT:
        draw_text(f"Final Score: {score} / {len(questions)}", 300, 200)
        if score >= 7:
            draw_text("Congratulations, you win!", 250, 250, (0, 200, 0))
            win_sound.play()
        else:
            draw_text("Better luck next time!", 250, 250, (200, 0, 0))
        play_again_rect = pygame.Rect(300, 400, 200, 50)
        pygame.draw.rect(screen, (0, 200, 0), play_again_rect)
        draw_text("Play Again", 350, 410, (255, 255, 255))

    pygame.display.flip()

async def main():
    setup()
    while True:
        update_loop()
        await asyncio.sleep(1.0 / 60)  # 60 FPS

if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())