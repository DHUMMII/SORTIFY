from customtkinter import *
from tkinter import filedialog, messagebox, StringVar
from PIL import Image
import sqlite3
import cv2
import numpy as np
import random
import os

# ---- DATABASE SETUP ------- #
conn = sqlite3.connect("sortify.db")
c = conn.cursor()

#credential table
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

#history table
c.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    category TEXT,
    item TEXT
)
""")

#feedback history table
c.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT
)
""")

# Eco points table for gamification
c.execute("""
CREATE TABLE IF NOT EXISTS eco_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    points INTEGER DEFAULT 0,
    FOREIGN KEY (username) REFERENCES users (username)
)
""")

#save changes
conn.commit()

# Classification logic 

def classify_with_opencv(image_path, description=""):
    """
    Takes in:
        image_path: Path to the uploaded image
        description: text description from user (optional)
    
    Returns:
        String: "Compostable", "Recyclable", "Reusable", "Trash", or "Unclear"
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return "Unclear"

        img = cv2.resize(img, (300, 300))
        
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)  # Better for color detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # For edge/texture analysis

        # COLOR BASED CLASSIFICATION 
        
        # GREEN DETECTION: Typically organic waste, bottles, or compostable items
        # HSV ranges: Hue 30-85 (green spectrum), Saturation 40-255, Value 40-255
        green_mask = cv2.inRange(hsv, np.array([30, 40, 40]), np.array([85, 255, 255]))
        green_ratio = cv2.countNonZero(green_mask) / (300 * 300)  # Percentage of green pixels

        # YELLOW DETECTION: Often indicates organic waste or certain plastics
        # HSV ranges: Hue 15-35 (yellow spectrum)
        yellow_mask = cv2.inRange(hsv, np.array([15, 60, 60]), np.array([35, 255, 255]))
        yellow_ratio = cv2.countNonZero(yellow_mask) / (300 * 300)

        # BLUE DETECTION: Common in recyclable plastic bottles and containers
        # HSV ranges: Hue 90-130 (blue spectrum)
        blue_mask = cv2.inRange(hsv, np.array([90, 60, 60]), np.array([130, 255, 255]))
        blue_ratio = cv2.countNonZero(blue_mask) / (300 * 300)

        # WHITE DETECTION: Paper, cardboard, clean containers
        # Uses grayscale thresholding - pixels above 200 intensity are considered white
        _, thresh_white = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        white_ratio = cv2.countNonZero(thresh_white) / (300 * 300)

        # EDGE DETECTION: High edge density often indicates manufactured items (recyclable)
        # Canny edge detection with thresholds 100-200 for good edge sensitivity
        edges = cv2.Canny(gray, 100, 200)
        edge_ratio = cv2.countNonZero(edges) / (300 * 300)

        # BROWN/WOOD DETECTION: For detecting reusable items like wooden objects, leather goods
        # HSV ranges: Hue 5-20 (brown/orange spectrum), moderate saturation and value
        brown_mask = cv2.inRange(hsv, np.array([5, 30, 30]), np.array([20, 200, 200]))
        brown_ratio = cv2.countNonZero(brown_mask) / (300 * 300)

        # TEXTURE ANALYSIS: Low texture variance often indicates smooth, intact reusable items
        # Calculate standard deviation of gray values - smooth objects have lower variance
        texture_variance = np.std(gray)

        if green_ratio > 0.12 or yellow_ratio > 0.12:
            category = "Compostable"
        elif brown_ratio > 0.10 and texture_variance < 45:  # Brown items with smooth texture = reusable
            category = "Reusable"
        elif edge_ratio > 0.25 and texture_variance < 40:  # High edges but smooth = intact reusable item
            category = "Reusable"
        elif blue_ratio > 0.08:  # Blue plastics/containers
            category = "Recyclable"
        elif white_ratio > 0.15:  # Paper/cardboard
            category = "Recyclable"
        elif edge_ratio > 0.25:  # High edge density = manufactured items
            category = "Recyclable"
        else:
            category = "Trash"


        #keywords which may be used in user's description

        keywords = {
            "Recyclable": [
                "plastic", "bottle", "paper", "box", "aluminum", "metal", 
                "cardboard", "glass", "can", "container"
            ],
            "Compostable": [
                "food", "fruit", "vegetable", "peel", "scraps", "leftover", 
                "rotten", "cotton", "moldy"
            ],
            "Reusable": [
                "jar", "bag", "clothes", "book", "toy", "furniture", "intact", 
                "good condition", "working", "clean", "reuse", "donate"
            ],
            "Trash": [
                "crushed", "broken", "cracked", "torn", "burnt", "melted"
            ]
        }

        # Check description for keywords and override visual classification if found
        desc = description.lower()
        for category, word_list in keywords.items():
            for word in word_list:
                if word in desc:
                    category = category  # Override with keyword-based classification
                    return category

    except Exception as e:
        print("OpenCV Error:", e)
        return "Unclear"

#  MAIN APPLICATION CLASS 

class SortifyApp:
    def __init__(self):
        set_appearance_mode("dark")
        set_default_color_theme("blue")

        self.root = CTk()
        self.root.title("Sortify - Eco-Friendly Waste Manager")
        self.root.geometry("500x500")
        self.root.resizable(False, False)

        self.current_user = None  # Tracks logged-in user
        self.image_path = None    # Stores path to selected image

        # Start with login screen
        self.login_page()
        self.root.mainloop()

    def clear_window(self):
        #helpr function to remove all widgets before switching pages
        for widget in self.root.winfo_children():
            widget.destroy()

    # Gamification methods
    def get_user_points(self, username):
        """Get current eco points for a user"""
        c.execute("SELECT points FROM eco_points WHERE username=?", (username,))
        result = c.fetchone()
        return result[0] if result else 0

    def add_points(self, username, points):
        """Add eco points to a user's account"""
        c.execute("SELECT points FROM eco_points WHERE username=?", (username,))
        result = c.fetchone()
        
        if result:
            # User exists, update points
            new_points = result[0] + points
            c.execute("UPDATE eco_points SET points=? WHERE username=?", (new_points, username))
        else:
            # New user, create entry
            c.execute("INSERT INTO eco_points (username, points) VALUES (?, ?)", (username, points))
        
        conn.commit()
        return self.get_user_points(username)

    def update_points_display(self):
        """Update the points display in the UI"""
        if hasattr(self, 'points_label'):
            current_points = self.get_user_points(self.current_user)
            self.points_label.configure(text=f"🌟 Eco Points: {current_points}")

    # ---- AUTHENTICATION PAGES --- 

    def login_page(self):
        self.clear_window()
        
        #Main design
        frame = CTkFrame(self.root, fg_color="#99b545", corner_radius=35)
        frame.pack(expand=True, fill="both", padx=50, pady=50)

        CTkLabel(frame, text="SORTIFY", font=("Arial",34,"bold")).pack(pady=(20,10))
        CTkLabel(frame, text="Log in to continue", font=("Arial",15)).pack(pady=(0,15))

        self.login_user = CTkEntry(frame, placeholder_text="Username", width=250, height=40, corner_radius=20)
        self.login_user.pack(pady=5)

        self.login_pass = CTkEntry(frame, placeholder_text="Password", width=250, height=40, show="*", corner_radius=20)
        self.login_pass.pack(pady=5)

        CTkButton(frame, text="Log In", width=250, height=40, fg_color="black", hover_color="#333", corner_radius=25,
                  command=self.check_login).pack(pady=(15,5))

        CTkLabel(frame, text="Don't have an account?", font=("Arial",13)).pack(pady=(10,5))

        CTkButton(frame, text="Sign Up", width=150, fg_color="black", hover_color="#333", height=35, corner_radius=25,
                  command=self.signup_page).pack()

    def signup_page(self):
        # the user registration interface
        self.clear_window()
        frame = CTkFrame(self.root, fg_color="#99b545", corner_radius=35)
        frame.pack(expand=True, fill="both", padx=50, pady=50)

        CTkLabel(frame, text="SORTIFY", font=("Arial",34,"bold")).pack(pady=(20,10))
        CTkLabel(frame, text="Create an account and join us!", font=("Arial",15)).pack(pady=(0,15))

        self.signup_user = CTkEntry(frame, placeholder_text="Username", width=250, height=40, corner_radius=20)
        self.signup_user.pack(pady=5)

        self.signup_pass = CTkEntry(frame, placeholder_text="Password", width=250, height=40, show="*", corner_radius=20)
        self.signup_pass.pack(pady=5)

        CTkButton(frame, text="Sign Up", width=250, height=40, fg_color="black", hover_color="#333", corner_radius=25,
                  command=self.register_user).pack(pady=(15,10))
    
        CTkButton(frame, text="Back to Login", width=150, height=40, fg_color="black", hover_color="#333", corner_radius=25,
                  command=self.login_page).pack(pady=10)

    # --------- MAIN APPLICATION WINDOW --------- 
    def main_window(self):
        
        self.clear_window()
        self.root.geometry("950x700")  # Expand window for main interface

        #navbar at the top
        navbar = CTkFrame(self.root, height=80)
        navbar.pack(fill="x", pady=10)

        CTkLabel(navbar, text=f"Sortify ♻️", font=("Arial",30,"bold")).pack(side="left", padx=20)

        CTkButton(navbar, text="Logout", hover_color="#b01b1b", width=100, corner_radius=25, 
                  command=self.logout).pack(side="right", padx=20)

        # Main container for 2-panel layout
        mainFrame = CTkFrame(self.root)
        mainFrame.pack(fill="both", expand=True, padx=10, pady=10)

        # LEFT PANEL
        leftPanel = CTkFrame(mainFrame, width=350, fg_color="#343636")
        leftPanel.pack(side="left", fill="y", padx=5, pady=5)

        CTkLabel(leftPanel, text="Upload Image", font=("Arial",15,"bold")).pack(pady=10)

        CTkButton(leftPanel, text="Choose File", width=200, corner_radius=25, command=self.choose_file).pack(pady=5)
        
        self.preview_label = CTkLabel(leftPanel, text="[No Image Selected]", width=280, height=120)
        self.preview_label.pack(pady=10)

        CTkLabel(leftPanel, text="Describe Item", font=("Arial",13,"bold")).pack(pady=(10,2))

        self.desc_box = CTkTextbox(leftPanel, height=40, width=260)
        self.desc_box.pack(pady=5)

        CTkButton(leftPanel, text="Classify Item", fg_color="#0e9a46", width=200, corner_radius=25, 
                  command=self.classify_item).pack(pady=15)
                  
        CTkButton(leftPanel, text="Generate Fun Fact!", fg_color="#0e9a46", width=200, corner_radius=25, 
                  command=self.generate_fun_fact).pack(pady=5)

        # RIGHT PANEL
        rightPanel = CTkScrollableFrame(mainFrame)
        rightPanel.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        CTkLabel(rightPanel, text="Classification Result", font=("Arial",15,"bold")).pack(pady=15)

        self.result_label = CTkLabel(rightPanel, text="Category: —", font=("Arial",20,"bold"))
        self.result_label.pack(pady=5)

        CTkLabel(rightPanel, text="Eco-friendly Tips", font=("Arial",14,"bold")).pack(pady=15)

        self.tip_label = CTkLabel(rightPanel, text="")
        self.tip_label.pack(padx=10, pady=10)

        feedback_frame = CTkFrame(rightPanel, height=150, fg_color="#343636", corner_radius=15)
        feedback_frame.pack(padx=10, pady=15, fill="x")
        
        CTkLabel(feedback_frame, text="Feedback on Prediction", font=("Arial",13,"bold")).pack(pady=5)
        
        self.feedback_var = StringVar(value="Correct")  # Default selection
        radios = CTkFrame(feedback_frame, fg_color="transparent")
        radios.pack(pady=5)

        for text in ["Correct", "Incorrect"]:
            CTkRadioButton(radios, text=text, variable=self.feedback_var, value=text).pack(side="left", padx=10)
        
        self.feedback_text = CTkTextbox(feedback_frame, height=60)
        self.feedback_text.pack(padx=10, pady=5, fill="x")
        
        CTkButton(feedback_frame, text="Submit Feedback", fg_color="#0e9a46", width=150, corner_radius=20,
                  command=self.submit_feedback).pack(pady=5)

        # Eco Points Display
        points_frame = CTkFrame(rightPanel, fg_color="#2b5797", corner_radius=15)
        points_frame.pack(padx=10, pady=10, fill="x")
        
        self.points_label = CTkLabel(points_frame, text="🌟 Eco Points: 0", font=("Arial",16,"bold"), text_color="white")
        self.points_label.pack(pady=10)
        
        # Update points display on window load
        self.update_points_display()

    # ADMIN DASHBOARD
    def admin_window(self):
        #this dashboard diplays all users and their feedback data
        self.clear_window()
        self.root.geometry("800x600")

        CTkLabel(self.root, text="Admin Dashboard", font=("Arial",28,"bold")).pack(pady=15)

        CTkButton(self.root, text="Logout", hover_color="#b01b1b", width=120, corner_radius=25,
                  command=self.logout).pack(side="top", padx=20, pady=10)

        frame = CTkScrollableFrame(self.root, width=700, height=500)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        CTkLabel(frame, text="All users", font=("Arial", 25, "bold")).pack(padx=10, pady=10)

        # Fetch and display all registered users
        c.execute("SELECT username FROM users")
        users = c.fetchall()

        for u in users:
            username = u[0]
            # Lambda capture technique to bind username to button command
            btn = CTkButton(frame, text=username, width=200, corner_radius=20,
                            command=lambda user=username: self.view_user_details(user))
            btn.pack(pady=5)

    def view_user_details(self, username):
        #admin can view correct and incorrect feedbacks of the user
        details = CTkToplevel(self.root)
        details.title(f"Details - {username}")
        details.geometry("600x500")

        c.execute("SELECT type, COUNT(*) FROM feedback WHERE username=? GROUP BY type", (username,))
        feedback_counts = dict(c.fetchall())  # Convert to dictionary for easy lookup
        
        # Extract counts with defaults for missing data
        correct_count = feedback_counts.get("Correct", 0)
        incorrect_count = feedback_counts.get("Incorrect", 0)

        # Get all feedback messages
        c.execute("SELECT type, message FROM feedback WHERE username=?", (username,))
        messages = c.fetchall()

        CTkLabel(details, text=f"User: {username}", font=("Arial",20,"bold")).pack(pady=10)
        CTkLabel(details, text=f"Correct Feedback: {correct_count}", font=("Arial",14)).pack(pady=5)
        CTkLabel(details, text=f"Incorrect Feedback: {incorrect_count}", font=("Arial",14)).pack(pady=5)

        msg_frame = CTkScrollableFrame(details, width=500, height=250)
        msg_frame.pack(pady=10, padx=10, fill="both", expand=True)

        for ftype, msg in messages:
            CTkLabel(msg_frame, text=f"[{ftype}] {msg}", anchor="w").pack(fill="x", pady=2, padx=5)

    # -- FUNCTIONALITY METHODS -- 
    
    def choose_file(self):
        # Open file dialog with image format filters
        self.image_path = filedialog.askopenfilename(
            title="Choose Image",
            filetypes=[("PNG files","*.png"),("JPG files","*.jpg"),("JPEG files","*.jpeg"),("All Files","*.*")]
        )
        
        if self.image_path:
            try:
                img = Image.open(self.image_path)
                ctk_img = CTkImage(light_image=img, dark_image=img, size=(260, 120)) #load and resize the image for preview
                self.preview_label.configure(image=ctk_img, text="")
                self.preview_label.image = ctk_img  # Keep reference
            except Exception as e:
                # Handles corrupted or unsupported image files
                self.preview_label.configure(text="Error loading image")
                print("Error:", e)

    def classify_item(self):
        # Ensure image is selected
        if not self.image_path:
            messagebox.showwarning("No Image", "Please upload an image first!")
            return

        # Get user description text
        description = self.desc_box.get("1.0","end").strip()
        
        # Call the core classification method
        category = classify_with_opencv(self.image_path, description)

        # Update UI with results
        self.result_label.configure(text=f"Category: {category}")
        tip = self.get_eco_tip(category)
        self.tip_label.configure(text=tip)

        # Store classification in user history 
        item_name = os.path.basename(self.image_path) 
        if description:
            item_name = f"{item_name} ({description})"

        # Insert into history table
        c.execute("INSERT INTO history (username, category, item) VALUES (?, ?, ?)",
                  (self.current_user, category, item_name))
        conn.commit()

        # Award eco points for uploading image
        new_points_total = self.add_points(self.current_user, 3)
        self.update_points_display()

        # Show results in popup for immediate feedback
        messagebox.showinfo("Result", f"Category: {category}\n\nTip: {tip}\n\n🌟 +3 Eco Points! Total: {new_points_total}")

    def generate_fun_fact(self):

        facts = [
            "Americans throw away 2.5 million plastic bottles every hour.",
            "A single plastic bag can take up to 1,000 years to decompose.",
            "Recycling one glass bottle saves enough energy to light a 100-watt bulb for 4 hours.",
            "The average person generates 4.5 pounds of waste per day.",
            "Composting can reduce household waste by up to 30%.",
            "It takes 95 percent less energy to recycle aluminum than to make it from raw materials.",
            "Food waste produces methane gas, which is 25 times more potent than CO2.",
            "Only 9 percent of all plastic ever produced has been recycled.",
            "E-waste is the fastest growing waste stream globally.",
            "Recycling one newspaper can save 1 cubic foot of landfill space.",
            "Reusing items just 5 times can reduce their environmental impact by 80%."
            ]
            
        messagebox.showinfo("Fun Fact", random.choice(facts))

    def get_eco_tip(self, category):

        tips = {
            "Recyclable": "Rinse bottles/containers and recycle in the correct bin.",
            "Compostable": "Compost organic waste to reduce landfill.",
            "Reusable": "Clean and reuse this item, or donate it to extend its life cycle.",
            "Trash": "Dispose in general waste, avoid mixing with recyclables."
        }
        return tips.get(category, "Dispose responsibly and recycle if possible.")

    def submit_feedback(self):
        # Collects and stores user feedback on classification accuracy
        
        feedback_type = self.feedback_var.get()  # Get radio button selection
        feedback_msg = self.feedback_text.get("1.0","end").strip()  # Get text content
        
        if feedback_msg:
            # Store feedback in database
            c.execute("INSERT INTO feedback (username, type, message) VALUES (?, ?, ?)",
                      (self.current_user, feedback_type, feedback_msg))
            conn.commit()
            
            # Award eco points for providing feedback
            new_points_total = self.add_points(self.current_user, 1)
            self.update_points_display()
            
            # Confirmation
            messagebox.showinfo("Feedback Submitted", f"Type: {feedback_type}\nMessage: {feedback_msg}\n\n🌟 +1 Eco Point! Total: {new_points_total}")
            self.feedback_text.delete("1.0","end")  # Clear text area
        else:
            messagebox.showwarning("Empty Feedback","Please write something before submitting.")

    def check_login(self):
        #Validates credentials
        user = self.login_user.get().strip()
        pw = self.login_pass.get().strip()

        #Checks for admin credentials   
        if user == "sortifyAdmin" and pw == "729099":
            self.current_user = user
            self.admin_window() 
            return

        # Check credentials against users table
        c.execute("SELECT 1 FROM users WHERE username=? AND password=?", (user, pw))
        if c.fetchone():  # If query returns a result, credentials are valid
            self.current_user = user
            self.main_window()  # Route to main application
        else:
            messagebox.showerror("Login Failed","Invalid username or password")

    def register_user(self):
        
        # Creates new account 
        user = self.signup_user.get().strip()
        pw = self.signup_pass.get().strip()

        if not user or not pw:
            messagebox.showwarning("Input Error", "All fields are required!")
            return

        try:
            # Inserting username and pw to the table
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, pw))
            conn.commit()
            messagebox.showinfo("Success", "Account created successfully! You can now log in.")
            self.login_page()  # Redirect to login
            
        except sqlite3.IntegrityError:
            # Handle duplicate username case
            messagebox.showerror("Error", "Username already exists. Please choose another.")

    def logout(self):
        # Reset application state
        self.current_user = None
        self.image_path = None

        # Return to login screen
        self.root.geometry("500x500")
        self.login_page()


if __name__ == "__main__":
    # Only run if this file is executed directly (not imported)
    SortifyApp()
