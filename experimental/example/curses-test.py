import curses

def main(stdscr):
    # Initialize curses
    curses.curs_set(0)  # Hide cursor
    stdscr.clear()

    # Get screen dimensions
    height, width = stdscr.getmaxyx()

    # Create two windows
    left_win = curses.newwin(height, width // 2, 0, 0)
    right_win = curses.newwin(height, width // 2, 0, width // 2)

    # Add content to windows
    left_win.addstr("Left Window")
    right_win.addstr("Right Window")

    # Refresh windows
    left_win.refresh()
    right_win.refresh()

    # Wait for a key press
    stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(main)