from customtkinter import *
from tkinter import filedialog, messagebox, StringVar
from PIL import Image
import sqlite3
import cv2
import numpy as np
import random
import os

# ---- DATABASE SETUP ---- 
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

conn.commit()

# Updated Classification logic with improved trash detection
def classify_with_opencv(image_path, description=""):
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {"Recyclable": 25, "Reusable": 25, "Compostable": 25, "Trash": 25}, "Trash"

        img = cv2.resize(img, (300, 300))
        
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Initialize probability scores
        recyclable_score = 0
        reusable_score = 0
        compostable_score = 0  # Added compostable category
        trash_score = 0

        # COLOR BASED CLASSIFICATION 
        
        # GREEN DETECTION: Typically organic waste, bottles, or compostable items
        green_mask = cv2.inRange(hsv, np.array([30, 40, 40]), np.array([85, 255, 255]))
        green_ratio = cv2.countNonZero(green_mask) / (300 * 300)

        # YELLOW DETECTION: Often indicates organic waste or certain plastics
        yellow_mask = cv2.inRange(hsv, np.array([15, 60, 60]), np.array([35, 255, 255]))
        yellow_ratio = cv2.countNonZero(yellow_mask) / (300 * 300)

        # BLUE DETECTION: Common in recyclable plastic bottles and containers
        blue_mask = cv2.inRange(hsv, np.array([90, 60, 60]), np.array([130, 255, 255]))
        blue_ratio = cv2.countNonZero(blue_mask) / (300 * 300)

        # WHITE DETECTION: Paper, cardboard, clean containers
        _, thresh_white = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        white_ratio = cv2.countNonZero(thresh_white) / (300 * 300)

        # EDGE DETECTION: High edge density often indicates manufactured items
        edges = cv2.Canny(gray, 100, 200)
        edge_ratio = cv2.countNonZero(edges) / (300 * 300)

        # BROWN/WOOD DETECTION: For detecting reusable items and organic matter
        brown_mask = cv2.inRange(hsv, np.array([5, 30, 30]), np.array([20, 200, 200]))
        brown_ratio = cv2.countNonZero(brown_mask) / (300 * 300)

        # TEXTURE ANALYSIS: Smooth surfaces often indicate intact items
        texture_variance = np.std(gray)

        # RED DETECTION: Often indicates warning labels or damaged items
        red_mask1 = cv2.inRange(hsv, np.array([0, 60, 60]), np.array([10, 255, 255]))
        red_mask2 = cv2.inRange(hsv, np.array([170, 60, 60]), np.array([180, 255, 255]))
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)
        red_ratio = cv2.countNonZero(red_mask) / (300 * 300)

        # ========== IMPROVED TRASH DETECTION LOGIC ==========
        
        # BLACK/DARK DETECTION: Dark colors often indicate burnt, dirty, or damaged items
        black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 50]))
        black_ratio = cv2.countNonZero(black_mask) / (300 * 300)
        
        # GREY DETECTION: Grey colors often indicate ash, dirt, or deteriorated items
        grey_mask = cv2.inRange(hsv, np.array([0, 0, 50]), np.array([180, 30, 150]))
        grey_ratio = cv2.countNonZero(grey_mask) / (300 * 300)
        
        # COLOR DIVERSITY ANALYSIS: Mixed colors often indicate messy waste
        # Calculate color histogram to detect color mixing
        hist_h = cv2.calcHist([hsv], [0], None, [180], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [256], [0, 256])
        hist_v = cv2.calcHist([hsv], [2], None, [256], [0, 256])
        
        # Count significant peaks in histograms (indicates multiple distinct colors)
        h_peaks = len([i for i in range(1, 179) if hist_h[i] > hist_h[i-1] and hist_h[i] > hist_h[i+1] and hist_h[i] > 500])
        s_peaks = len([i for i in range(1, 255) if hist_s[i] > hist_s[i-1] and hist_s[i] > hist_s[i+1] and hist_s[i] > 500])
        
        color_diversity = (h_peaks + s_peaks) / 2  # Average peaks across hue and saturation
        
        # BRIGHTNESS INCONSISTENCY: Irregular lighting suggests damaged/dirty items
        brightness_std = np.std(hsv[:,:,2])  # Standard deviation of brightness values
        
        # SATURATION ANALYSIS: Very low saturation often indicates faded/old items
        low_sat_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 50, 255]))
        low_sat_ratio = cv2.countNonZero(low_sat_mask) / (300 * 300)
        
        # NOISE/GRAIN DETECTION: Noisy images often indicate damaged items
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        noise_level = np.var(laplacian)

        # SCORING SYSTEM BASED ON VISUAL FEATURES

        # ========== STRICT TRASH SCORING ==========
        
        # High black content = likely burnt, very dirty, or damaged
        if black_ratio > 0.15:  # More than 15% black pixels
            trash_score += 40
        elif black_ratio > 0.08:  # More than 8% black pixels
            trash_score += 25
            
        # High grey content = likely ash, dirt, or deteriorated
        if grey_ratio > 0.20:  # More than 20% grey pixels
            trash_score += 35
        elif grey_ratio > 0.12:  # More than 12% grey pixels
            trash_score += 20
            
        # Color diversity indicates mixed waste/messy items
        if color_diversity > 8:  # Many different colors mixed together
            trash_score += 30
        elif color_diversity > 5:
            trash_score += 15
            
        # Very high texture variance = damaged/deteriorated surfaces
        if texture_variance > 70:
            trash_score += 35
        elif texture_variance > 50:
            trash_score += 20
            
        # Brightness inconsistency = irregular/damaged items
        if brightness_std > 60:
            trash_score += 25
        elif brightness_std > 40:
            trash_score += 15
            
        # Very low saturation = faded/old items
        if low_sat_ratio > 0.60:  # More than 60% unsaturated
            trash_score += 30
        elif low_sat_ratio > 0.40:  # More than 40% unsaturated
            trash_score += 15
            
        # High noise level = poor quality/damaged items
        if noise_level > 800:
            trash_score += 25
        elif noise_level > 500:
            trash_score += 15
            
        # Combination penalties (these are especially strong trash indicators)
        if black_ratio > 0.10 and grey_ratio > 0.15:  # Lots of black AND grey
            trash_score += 50
            
        if color_diversity > 6 and texture_variance > 60:  # Mixed colors AND rough texture
            trash_score += 40
            
        if low_sat_ratio > 0.50 and brightness_std > 50:  # Faded AND inconsistent lighting
            trash_score += 35

        # Traditional trash indicators (keep existing logic but reduce weights)
        if red_ratio > 0.05:  # Red often indicates warnings/damage
            trash_score += 10
        if edge_ratio < 0.10:  # Low edge density might indicate formless waste
            trash_score += 10

        # ========== COMPOSTABLE INDICATORS ==========
        
        # High green/yellow content often indicates organic matter
        if green_ratio > 0.20 and yellow_ratio > 0.15:  # Lots of green AND yellow
            compostable_score += 40
        elif green_ratio > 0.15:  # Significant green content
            compostable_score += 25
        elif yellow_ratio > 0.20:  # Significant yellow content
            compostable_score += 20
            
        # Brown content can indicate organic matter (leaves, food scraps, etc.)
        if brown_ratio > 0.15 and texture_variance > 30:  # Brown with some texture variation
            compostable_score += 30
        elif brown_ratio > 0.10:
            compostable_score += 15
            
        # Moderate texture variance might indicate organic textures
        if 25 < texture_variance < 55:  # Not too smooth, not too rough
            compostable_score += 15

        # ========== RECYCLABLE/REUSABLE INDICATORS (with trash penalties) ==========
        
        # Reduce recyclable/reusable scores if trash indicators are strong
        trash_penalty_factor = 1.0
        if black_ratio > 0.12 or grey_ratio > 0.18 or color_diversity > 7:
            trash_penalty_factor = 0.3  # Heavily reduce recyclable/reusable chances
        elif black_ratio > 0.08 or grey_ratio > 0.12 or color_diversity > 5:
            trash_penalty_factor = 0.6  # Moderately reduce recyclable/reusable chances

        # Recyclable indicators (with trash penalties applied)
        if blue_ratio > 0.08 and trash_penalty_factor > 0.5:  # Blue plastics (if not too trashy)
            recyclable_score += int(25 * trash_penalty_factor)
        if white_ratio > 0.15 and texture_variance < 50:  # Clean paper/cardboard
            recyclable_score += int(20 * trash_penalty_factor)
        if edge_ratio > 0.20 and texture_variance < 60:  # Manufactured items with clear edges
            recyclable_score += int(15 * trash_penalty_factor)
        if green_ratio > 0.05 and green_ratio < 0.15 and black_ratio < 0.08:  # Clean green containers
            recyclable_score += int(20 * trash_penalty_factor)

        # Reusable indicators
        if brown_ratio > 0.08 and texture_variance < 45:  # Clean wood/leather items
            reusable_score += int(25 * trash_penalty_factor)
        if texture_variance < 35 and edge_ratio > 0.15 and black_ratio < 0.05:  # Smooth, intact objects
            reusable_score += int(20 * trash_penalty_factor)
        if edge_ratio > 0.25 and texture_variance < 40 and brightness_std < 30:  # Clear, well-lit objects
            reusable_score += int(15 * trash_penalty_factor)
        if white_ratio > 0.20 and texture_variance < 30 and low_sat_ratio < 0.30:  # Clean, vibrant items
            reusable_score += int(10 * trash_penalty_factor)

        # KEYWORD ANALYSIS FROM DESCRIPTION (strengthen trash keywords)
        keywords = {
            "Recyclable": [
                "plastic", "bottle", "paper", "box", "aluminum", "metal", 
                "cardboard", "glass", "can", "container", "clean", "empty"
            ],
            "Reusable": [
                "jar", "bag", "clothes", "book", "toy", "furniture", "intact", "cardboard"
                "good condition", "working", "reuse", "donate", "functional"
            ],
            "Compostable": [
                "food", "organic", "banana", "apple", "fruit", "vegetable", 
                "leaves", "grass", "coffee grounds", "tea bags", "eggshells",
                "biodegradable", "compost", "natural", "plant"
            ],
            "Trash": [
                "broken", "cracked", "torn", "burnt", "melted", "dirty", 
                "damaged", "rotten", "moldy", "waste", "garbage", "rubbish",
                "spoiled", "contaminated", "stained", "smelly", "decomposed",
                "rusty", "corroded", "shattered", "destroyed", "unusable"
            ]
        }

        desc = description.lower()
        for category, word_list in keywords.items():
            for word in word_list:
                if word in desc:
                    if category == "Recyclable":
                        recyclable_score += int(20 * trash_penalty_factor)
                    elif category == "Reusable":
                        reusable_score += int(20 * trash_penalty_factor)
                    elif category == "Compostable":
                        compostable_score += 30  # Strong boost for compostable keywords
                    elif category == "Trash":
                        trash_score += 40  # Strong boost for trash keywords

        # Base scores to ensure total doesn't become 0
        recyclable_score += 5
        reusable_score += 5  
        compostable_score += 5
        trash_score += 5

        # Calculate total and percentages
        total_score = recyclable_score + reusable_score + compostable_score + trash_score
        
        recyclable_percent = int((recyclable_score / total_score) * 100)
        reusable_percent = int((reusable_score / total_score) * 100) 
        compostable_percent = int((compostable_score / total_score) * 100)
        trash_percent = 100 - recyclable_percent - reusable_percent - compostable_percent

        probabilities = {
            "Recyclable": recyclable_percent,
            "Reusable": reusable_percent, 
            "Compostable": compostable_percent,
            "Trash": trash_percent
        }

        # Determine most likely category
        most_likely = max(probabilities, key=probabilities.get)

        return probabilities, most_likely

    except Exception as e:
        print("OpenCV Error:", e)
        # Return equal probabilities if error occurs
        return {"Recyclable": 25, "Reusable": 25, "Compostable": 25, "Trash": 25}, "Trash"

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

        self.login_page()
        self.root.mainloop()

    def clear_window(self):
        #helpr function to remove all widgets before switching pages
        for widget in self.root.winfo_children():
            widget.destroy()

    def get_user_points(self, username):
        c.execute("SELECT points FROM eco_points WHERE username=?", (username,))
        result = c.fetchone()
        return result[0] if result else 0

    def add_points(self, username, points):
        c.execute("SELECT points FROM eco_points WHERE username=?", (username,))
        result = c.fetchone()
        
        if result:
            new_points = result[0] + points
            c.execute("UPDATE eco_points SET points=? WHERE username=?", (new_points, username))
        else:
            c.execute("INSERT INTO eco_points (username, points) VALUES (?, ?)", (username, points))
        
        conn.commit()
        return self.get_user_points(username)

    def update_points_display(self):
        """Update the points display in the UI"""
        if hasattr(self, 'points_label'):
            current_points = self.get_user_points(self.current_user)
            self.points_label.configure(text=f"🌟 Eco Points: {current_points}")

    # ---- AUTHENTICATION PAGES -- 

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
        self.root.geometry("950x700")  

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

        # Probability display frame
        self.prob_frame = CTkFrame(rightPanel, fg_color="#2d3748", corner_radius=15)
        self.prob_frame.pack(padx=10, pady=10, fill="x")

        CTkLabel(self.prob_frame, text="Probability Analysis", font=("Arial",14,"bold")).pack(pady=5)

        self.prob_labels = {}
        for category in ["Recyclable", "Reusable", "Compostable", "Trash"]:
            label = CTkLabel(self.prob_frame, text=f"{category}: —%", font=("Arial",12))
            label.pack(pady=2)
            self.prob_labels[category] = label

        CTkLabel(rightPanel, text="Eco-friendly Tips", font=("Arial",14,"bold")).pack(pady=15)

        self.tip_label = CTkLabel(rightPanel, text="")
        self.tip_label.pack(padx=10, pady=10)

        feedback_frame = CTkFrame(rightPanel, height=150, fg_color="#343636", corner_radius=15)
        feedback_frame.pack(padx=10, pady=15, fill="x")
        
        CTkLabel(feedback_frame, text="Feedback on Prediction", font=("Arial",13,"bold")).pack(pady=5)
        
        self.feedback_var = StringVar(value="Correct")  #by default "correct" is checked
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
        
        self.update_points_display()

    # ADMIN DASHBOARD
    def admin_window(self):
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
            # Lambda fucntion to bind username to button command
            btn = CTkButton(frame, text=username, width=200, corner_radius=20,
                            command=lambda user=username: self.view_user_details(user))
            btn.pack(pady=5)

    def view_user_details(self, username):
        details = CTkToplevel(self.root)
        details.title(f"Details - {username}")
        details.geometry("600x500")

        c.execute("SELECT type, COUNT(*) FROM feedback WHERE username=? GROUP BY type", (username,))
        feedback_counts = dict(c.fetchall())  
        
        correct_count = feedback_counts.get("Correct", 0)
        incorrect_count = feedback_counts.get("Incorrect", 0)

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
                self.preview_label.configure(text="Error loading image")
                print("Error:", e)

    def classify_item(self):
        if not self.image_path:
            messagebox.showwarning("No Image", "Please upload an image first!")
            return

        description = self.desc_box.get("1.0","end").strip()
        
        probabilities, most_likely_category = classify_with_opencv(self.image_path, description)

        # Update result display
        self.result_label.configure(text=f"Most Likely: {most_likely_category}")
        
        # Update probability labels
        for category, percentage in probabilities.items():
            self.prob_labels[category].configure(text=f"{category}: {percentage}%")

        tip = self.get_eco_tip(most_likely_category)
        self.tip_label.configure(text=tip)

        item_name = os.path.basename(self.image_path) 
        if description:
            item_name = f"{item_name} ({description})"

        c.execute("INSERT INTO history (username, category, item) VALUES (?, ?, ?)",
                  (self.current_user, most_likely_category, item_name))
        conn.commit()

        new_points_total = self.add_points(self.current_user, 3)
        self.update_points_display()

        # Create probability display string for messagebox
        prob_text = f"Recyclable: {probabilities['Recyclable']}%\nReusable: {probabilities['Reusable']}%\nCompostable: {probabilities['Compostable']}%\nTrash: {probabilities['Trash']}%"
        
        messagebox.showinfo("Result", f"Analysis Complete!\n\n{prob_text}\n\nMost Likely: {most_likely_category}\n\nTip: {tip}\n\n +3 Eco Points! Total: {new_points_total}")

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
            "Reusable": "Clean and reuse this item, or donate it to extend its life cycle.",
            "Compostable": "Compost this organic waste to reduce landfill and create nutrient-rich soil.",
            "Trash": "Dispose in general waste, avoid mixing with recyclables."
        }
        return tips.get(category, "Dispose responsibly and recycle if possible.")

    def submit_feedback(self):
        
        feedback_type = self.feedback_var.get()  
        feedback_msg = self.feedback_text.get("1.0","end").strip()  # Get text content
        
        if feedback_msg:
            c.execute("INSERT INTO feedback (username, type, message) VALUES (?, ?, ?)",
                      (self.current_user, feedback_type, feedback_msg))
            conn.commit()
            
            new_points_total = self.add_points(self.current_user, 1)
            self.update_points_display()
            
            messagebox.showinfo("Feedback Submitted", f"Type: {feedback_type}\nMessage: {feedback_msg}\n\n🌟 +1 Eco Point! Total: {new_points_total}")
            self.feedback_text.delete("1.0","end")  # Clear text area
        else:
            messagebox.showwarning("Empty Feedback","Please write something before submitting.")

    def check_login(self):
        user = self.login_user.get().strip()
        pw = self.login_pass.get().strip()

        if user == "sortifyAdmin" and pw == "729099":
            self.current_user = user
            self.admin_window() 
            return

        c.execute("SELECT 1 FROM users WHERE username=? AND password=?", (user, pw))
        if c.fetchone(): 
            self.current_user = user
            self.main_window()  # Route to main application
        else:
            messagebox.showerror("Login Failed","Invalid username or password")

    def register_user(self):
        user = self.signup_user.get().strip()
        pw = self.signup_pass.get().strip()

        if not user or not pw:
            messagebox.showwarning("Input Error", "All fields are required!")
            return

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, pw))
            conn.commit()
            messagebox.showinfo("Success", "Account created successfully!")
            self.current_user = user  # Set current user after successful registration
            self.main_window()  # Route to main application

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
    SortifyApp()
