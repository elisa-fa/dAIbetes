import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from datetime import datetime
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import ollama
from PIL import Image, ImageOps
import io

# FUNCTION: BRAIN
@st.cache_resource
def init_diabetes_ai():
    persist_dir = "./db_diabetes_en"
    embeddings = OllamaEmbeddings(model="nomic-embed-text")

    # 1. If the database already exists on disk, just load it!
    # This prevents Chroma from trying to re-create 'bindings' and crashing.
    if os.path.exists(persist_dir) and os.listdir(persist_dir):
        return Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    
    # 2. Only if it doesn't exist, we create it
    loader = TextLoader("diabetesKnowledge.md")
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)
    
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    return vectorstore

def get_gemma_response(user_query, vectorstore):
    relevant_info = vectorstore.similarity_search(user_query, k=3)
    context = "\n\n".join([doc.page_content for doc in relevant_info])
    
    # System Prompt potenziato: agisce, non spiega le regole
    system_prompt = f"""
    You are Gemma, a supportive and professional Diabetes Assistant. 
    
    CRITICAL RULES:
    1. NEVER mention the "context" or "provided documents" to the user. Answer naturally.
    2. If a user reports symptoms of hypoglycemia (dizziness, sweating, confusion) or hyperglycemia, IMMEDIATELY tell them to check their blood sugar and contact a doctor if they are in danger.
    3. Use the following medical data to provide answers: {context}
    4. If the information is not in the data, say you don't know and advise consulting a specialist.
    5. Always maintain a helpful, peer-to-peer but professional tone.
    """
    
    response = ollama.generate(model="gemma4", system=system_prompt, prompt=user_query)
    return response['response']

def analyze_history_with_gemma(meals_df, bg_df, vectorstore):
    # Prepare the data context
    meals_context = meals_df.tail(7).to_string() if not meals_df.empty else "No meals logged."
    bg_context = bg_df.tail(7).to_string() if not bg_df.empty else "No glucose readings logged."
    
    # Retrieval step: Get I:C adjustment rules from the MD file
    relevant_protocol = vectorstore.similarity_search("How to adjust I:C ratio based on hyperglycemia", k=1)
    protocol_text = relevant_protocol[0].page_content

    prompt = f"""
    You are a Medical Data Analyst. Analyze the following patient history:
    
    MEAL HISTORY (Last 7 entries):
    {meals_context}
    
    GLUCOSE HISTORY (Last 7 entries):
    {bg_context}
    
    MEDICAL PROTOCOL FOR ADJUSTMENTS:
    {protocol_text}
    
    TASK:
    1. Identify if there is a recurring pattern of Hyperglycemia or Hypoglycemia.
    2. Suggest if the I:C ratio or Sensitivity factor needs adjustment.
    3. Keep it professional, concise, and always end with a medical disclaimer.
    DO NOT mention you are reading a context. Talk directly to the patient.
    """
    
    response = ollama.generate(model="gemma4", prompt=prompt)
    return response['response']


def analyze_image_with_vision(uploaded_file, mode="Meal"):
    # 1. Carichiamo l'immagine con PIL per gestire rotazione e qualità
    img = Image.open(uploaded_file)
    
    # Raddrizza l'immagine se il telefono l'ha salvata girata (EXIF orientation)
    img = ImageOps.exif_transpose(img)
    
    # Se l'immagine è enorme, la ridimensioniamo mantenendo i dettagli (es. 1000px)
    # Ma non troppo piccola come fa Streamlit di default!
    img.thumbnail((1000, 1000))
    
    # Convertiamo in byte per Ollama
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95) # Alta qualità
    image_bytes = buf.getvalue()

    model_vision = "llava" # Llava è meglio di Moondream per il testo

    if mode == "Meal":
        prompt = "Identify the main food and estimate its weight. Be concise."
    else:
        # Prompt super specifico per etichette italiane
        prompt = """
        This is an Italian nutrition label. 
        Focus ONLY on 'Carboidrati' (per 100g).
        Tell me ONLY the number. 
        If you see 'di cui zuccheri', ignore it, I want the total 'Carboidrati'.
        Output example: '65'.
        """

    try:
        response = ollama.generate(model=model_vision, prompt=prompt, images=[image_bytes])
        return response['response'].strip()
    except Exception as e:
        return f"Error: {str(e)}"



# --- STYLE AND CONFIGURATION ---
st.set_page_config(page_title="Gemma Diabetes AI", page_icon="🩺", layout="wide")

# LOCAL FILES TO SAVE THE DATA (Privacy)
USER_DATA_FILE = "user_settings.json"
MEALS_LOG_FILE = "meals_history.csv"
BG_LOG_FILE = "blood_sugar_history.csv"

def load_bg_data():
    if os.path.exists(BG_LOG_FILE):
        return pd.read_csv(BG_LOG_FILE)
    return pd.DataFrame(columns=["Date", "Reading_mgdL", "Note"])

# --- SUPPORT FUNCTIONS ---
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    return {"name": "User", "ic_ratio": 14.0}

def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f)

def load_meals():
    if os.path.exists(MEALS_LOG_FILE):
        return pd.read_csv(MEALS_LOG_FILE)
    return pd.DataFrame(columns=["Date", "Meal", "CHO_g", "Insulin_U"])

FOOD_DB_FILE = "custom_food_db.json"

def load_food_db():
    # Database
    default_db = {
        "Pasta, Rice, Cereals, Baked Goods": 80,
        "Bread, Flour, Spelt, Snacks": 70,
        "Jam, Nutella": 60,
        "Legumes, Pizza, Croissants, Chocolate": 50,
        "Banana, Persimmon, Grape, Fig": 15,
        "Pear, Apple, Pineapple, Kiwi": 10,
        "Apricot, Peach, Orange, Melon": 7,
        "Soda (Coke, Orange Soda)": 10,
        "Milk": 5
    }
    if os.path.exists(FOOD_DB_FILE):
        with open(FOOD_DB_FILE, "r") as f:
            return json.load(f)
    return default_db

def save_food_db(db):
    with open(FOOD_DB_FILE, "w") as f:
        json.dump(db, f)

# Loading food database
food_db = load_food_db()

# --- LOADING INITIAL DATA ---
user_data = load_user_data()
meals_df = load_meals()

# --- SIDEBAR (Account & Settings) ---
st.sidebar.title("👤 My Account")

# Loading 3 fundamentals
initial_name = user_data.get("name", "Elisa")
initial_ratio = float(user_data.get("ic_ratio", 14.0))        # For food
initial_sens = float(user_data.get("sensitivity", 40.0))    # for corrections

new_name = st.sidebar.text_input("Name", value=initial_name)

# Widget ratio (I:C)
new_ratio = st.sidebar.number_input("I:C Ratio (1 unit : X grams)", 
                                    value=initial_ratio, step=0.5)

# Widget sensibility (ISF)
new_sensitivity = st.sidebar.number_input("Sensitivity Factor (1 unit : -X mg/dL)", 
                                          value=initial_sens, step=1.0)

if st.sidebar.button("Save Profile"):
    save_user_data({
        "name": new_name, 
        "ic_ratio": new_ratio, 
        "sensitivity": new_sensitivity
    })
    st.sidebar.success("Profile Updated!")

st.sidebar.divider()
menu = st.sidebar.radio("Navigate", [
    "📖 User Guide",
    "🏠 Dashboard",   
    "💬 Medical Chat", 
    "🧮 Insulin Calculator", 
    "💉 Active Insulin Correction",
    "🩸 Log Blood Sugar", 
    "📊 My History", 
    "🆘 Safety Protocols"
])
# --- SECTION: USER GUIDE ---
if menu == "📖 User Guide":
    st.title("📖 App Guide & Medical Concepts")
    
    # MANDATORY DISCLAIMER
    st.error("""
    **⚠️ MEDICAL DISCLAIMER** This application is **NOT a medical device**. It is a support tool designed for educational and informational purposes only. 
    All calculations are estimates based on the data you provide. **Always follow your doctor's specific instructions.** In case of a medical emergency or severe symptoms, contact emergency services or your healthcare provider immediately.
    """)

    st.divider()

    # 1. Account Creation & Parameters
    with st.expander("1. Account Setup: Understanding I:C and Sensitivity", expanded=True):
        st.markdown("""
        To use the calculators, you must set two fundamental parameters in the sidebar:
        
        * **I:C Ratio (Insulin-to-Carbohydrate):** Defines how many grams of carbohydrates are "covered" by 1 unit of rapid-acting insulin.  
            *Example:* If your ratio is **14**, 1 unit of insulin will manage 14g of carbs. This helps you calculate mealtime doses.
        
        * **Sensitivity Factor (ISF - Insulin Sensitivity Factor):** Defines how many mg/dL your blood sugar drops with 1 unit of insulin.  
            *Example:* If your factor is **40**, 1 unit of insulin will lower your blood glucose by 40 mg/dL. This is used for **correcting high blood sugar** between meals.
        """)
        

    # 2. Dashboard
    with st.expander("2. 🏠 Dashboard"):
        st.write("""
        The Dashboard is your control center. It shows:
        * Your currently saved medical parameters.
        * A quick summary of your logged activity (last meal and total entries).
        * Quick navigation tips to get started.
        """)

    # 3. Medical Chat
    with st.expander("3. 💬 Medical Chat"):
        st.write("""
        This is an AI-powered assistant based on **Gemma 4**. It is trained on specific medical 
        guidelines (AMD-SID 2024). You can ask it about:
        * Carbohydrate content of specific foods.
        * Clarifications on glycemic index.
        * General diabetes management advice.
        """)

    # 4. Insulin Calculator (Mealtime)
    with st.expander("4. 🧮 Insulin Calculator"):
        st.write("""
        You can use this before eating. You select the food type and weight (or upload a picture of it), and the app uses your 
        **I:C Ratio** to suggest the insulin dose. It also allows you to add custom foods 
        to your personal database.
        Moreover, you can compare your glucose pre-meal reading with your 2h post-meal glucose reading to evaluate your I:C ratio.
        """)

    # 5. Active Insulin Correction (Non-Preprandial)
    with st.expander("5. 💉 Active Insulin Correction"):
        st.write("""
        Use this if your sugar is high **between meals**. 
        This tool is special because it calculates **Insulin on Board (IOB)**. It prevents 
        "insulin stacking" by reducing the correction dose if your previous meal-time 
        insulin is still active (within a 5-hour window).
        """)
        

    # 6. Logging 
    with st.expander("6. 🩸 Logging"):
        st.write("""
        Use this section to log your glucose readings at different moments (Fasting, Pre-meal, etc.). This will help
        you keep track of your glucose levels throughout the week.
        """)

    # 7. History
    with st.expander("7. 📊 History"):
        st.write("""
        Visualize your progress. The app generates charts showing your glucose trends relative to target ranges and carbohydrates intake over time.
        In addition, the 'Gemma AI Health Insight' tool creates a an AI clinical report based on your logged data.
        """)

    # 8. Safety Protocols
    with st.expander("8. 🆘 Safety Protocols"):
        st.write("""
        A quick-access guide for emergencies. It explains the **Rule of 15** for Hypoglycemia 
        and the steps to take for Hyperglycemia.
        """)

# --- SECTION 1: DASHBOARD ---
elif menu == "🏠 Dashboard":
    # Using new_name, the variable defined in the widget text_input
    st.title(f"Welcome back, {new_name}!") 
    col1, col2, col3 = st.columns(3)
    col1.metric("Current I:C Ratio", f"1:{new_ratio}")
    col2.metric("Meals Logged", len(meals_df))
    if not meals_df.empty:
        last_meal = meals_df.iloc[-1]["Meal"]
        col3.metric("Last Meal", last_meal)
    else:
        col3.metric("Last Meal", "None")
    
    st.info("Use the sidebar to navigate through the app features.")

# --- SECTION 2: CHAT (RAG) ---
elif menu == "💬 Medical Chat":
    st.title("💬 Diabetes Knowledge Chat")
    st.write("Ask Gemma about nutrition, I:C ratio adjustments, or safety protocols.")
    
    # Initialize the AI Brain
    vectorstore = init_diabetes_ai()
    
    # Chat Interface
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # User input
    if prompt := st.chat_input("What is your question?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Gemma is thinking..."):
                response = get_gemma_response(prompt, vectorstore)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

# --- SECTION 3: CALCULATOR ---
elif menu == "🧮 Insulin Calculator":
    st.title("🧮 AI Insulin Calculator")
    
    # --- PART 1: VISION (IDENTIFICATION) ---
    st.subheader("📸 Meal Analysis")
    uploaded_image = st.file_uploader("Upload a photo of your meal", type=['jpg', 'jpeg', 'png'])
    
    # Initialize empty AI variables
    ai_food_name = ""
    ai_weight = 0.0
    ai_cho_per_100 = 0.0

    if uploaded_image:
        st.image(uploaded_image, width=300)
        with st.spinner("Gemma is analyzing your meal..."):
            vision_result = analyze_image_with_vision(uploaded_image)
            st.info(f"**Recognized:** {vision_result}")
            
            # Ask Gemma 4 to extract data in JSON format for the form
            p_res = ollama.generate(
                model="gemma4", 
                prompt=f"Extract food and weight from '{vision_result}'. Return ONLY JSON: {{\"food\": \"name\", \"weight\": 150}}"
            )
            try:
                data = json.loads(p_res['response'])
                # Use .get() to avoid errors if keys are missing
                ai_food_name = data.get('food', "")
                ai_weight = float(data.get('weight', 0.0))
                
                # If the food is in the DB, get the carbs; otherwise, ask Gemma
                if ai_food_name in food_db:
                    ai_cho_per_100 = food_db[ai_food_name]
                else:
                    est_res = ollama.generate(model="gemma4", prompt=f"CHO per 100g for {ai_food_name}? Just the number.")
                    # Extract only numbers and dots from the response
                    ai_cho_per_100 = float(''.join(c for c in est_res['response'] if c.isdigit() or c == '.'))
            except:
                pass

    st.divider()

    # --- PART 2: ADD ITEM TO CURRENT MEAL ---
    st.subheader("🥣 Step 2: Add Items to your Plate")

    # Inizializziamo la lista del pasto corrente se non esiste
    if "current_meal_items" not in st.session_state:
        st.session_state.current_meal_items = []
    
    food_options = list(food_db.keys()) + ["Other"]
    try:
        default_idx = food_options.index(ai_food_name) if ai_food_name in food_db else len(food_options)-1
    except:
        default_idx = len(food_options) - 1

    selected_food = st.selectbox("Select Food", food_options, index=default_idx)
    
    col1, col2 = st.columns(2)
    if selected_food == "Other":
        final_name = col1.text_input("Name", value=ai_food_name)
        cho_val = col2.number_input("CHO/100g", value=ai_cho_per_100, step=1.0)
    else:
        final_name = selected_food
        cho_val = food_db[selected_food]
        col1.markdown(f"Value: **{cho_val}g** CHO/100g")

    weight = st.number_input("Weight (g)", min_value=0.0, value=ai_weight, step=10.0)

    if st.button("➕ Add to Current Meal"):
        if weight > 0 and cho_val > 0:
            item_cho = (weight * cho_val) / 100
            st.session_state.current_meal_items.append({
                "item": final_name,
                "weight": weight,
                "cho": item_cho
            })
            st.toast(f"Added {final_name}!")
        else:
            st.error("Enter valid weight and CHO.")

    # --- PART 3: SUMMARY & FINAL CALCULATION ---
    if st.session_state.current_meal_items:
        st.divider()
        st.subheader("🍽️ Your Plate Summary")
        
        # Mostriamo la tabella degli alimenti aggiunti
        temp_df = pd.DataFrame(st.session_state.current_meal_items)
        st.table(temp_df)
        
        # Calcoli totali
        total_meal_cho = sum(item['cho'] for item in st.session_state.current_meal_items)
        # Qui usiamo il 'new_ratio' (I:C) definito nel tuo profilo
        final_insulin = round(total_meal_cho / new_ratio, 1)

        # Visualizzazione affiancata per Carbo e Insulina
        col_res1, col_res2 = st.columns(2)
        col_res1.metric("Total Carbs", f"{round(total_meal_cho, 1)} g")
        col_res2.metric("Suggested Insulin Dose", f"{final_insulin} Units", delta_color="inverse")
        
        st.info(f"Calculation based on your I:C Ratio (1:{new_ratio})")
        
        st.divider()
        col_end1, col_end2 = st.columns(2)
        
        if col_end1.button("✅ Confirm & Log Full Meal", type="primary"):
            # Salvataggio nel log
            meal_summary_name = ", ".join([item['item'] for item in st.session_state.current_meal_items])
            new_row = {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                "Meal": meal_summary_name, 
                "CHO_g": round(total_meal_cho, 1), 
                "Insulin_U": final_insulin
            }
            meals_df = pd.concat([meals_df, pd.DataFrame([new_row])], ignore_index=True)
            meals_df.to_csv(MEALS_LOG_FILE, index=False)
            
            # Reset e refresh
            st.session_state.current_meal_items = []
            st.success(f"Meal logged: {final_insulin} units administered.")
            st.rerun() 

        if col_end2.button("🗑️ Clear All"):
            st.session_state.current_meal_items = []
            st.rerun()

    # --- 3. POST-MEAL ANALYSIS ---
    st.divider()
    st.subheader("🩸 Post-Meal Glycemic Analysis (2h)")
    
    with st.expander("Evaluate your I:C Ratio Accuracy", expanded=True):
        c1, c2 = st.columns(2)
        pre_bg = c1.number_input("Pre-meal Glucose (mg/dL)", min_value=0, key="pre_bg_calc")
        post_2h = c2.number_input("2h Post-meal Glucose (mg/dL)", min_value=0, key="post_bg_calc")
        
        if st.button("Analyze Ratio Results"):
            if pre_bg > 0 and post_2h > 0:
                # Safety checks
                if pre_bg < 70 or post_2h < 70:
                    st.error("🚨 HYPOGLYCEMIA DETECTED! Follow emergency protocol.")
                elif pre_bg > 130:
                    st.warning("⚠️ High starting glucose (Fasting/Pre-meal).")
                
                diff = post_2h - pre_bg
                st.write(f"Glucose variance: **+{diff} mg/dL**")
                
                if diff > 50:
                    st.error("❌ I:C Ratio too weak (High increase). Consider LOWERING your ratio.")
                elif diff < 0:
                    st.warning("❌ I:C Ratio too strong (Drop detected). Consider INCREASING your ratio.")
                else:
                    st.success("✅ Target Met! Your ratio seems accurate.")
            else:
                st.info("Enter both values to see the analysis.")


# -- SECTION 4 - ACTIVE INSULINE CORRECTION --
elif menu == "💉 Active Insulin Correction":
    st.title("💉 Non-Preprandial Correction")
    st.info("Use this if you have high blood sugar but it's NOT time for a meal yet. This accounts for 'Insulin on Board' to prevent hypoglycemia.")

    # 1. Input Data
    col1, col2 = st.columns(2)
    current_bg = col1.number_input("Current Blood Glucose (mg/dL)", min_value=0)
    
    # Time options from your table
    time_options = {
        "1 hour": {"reduction": 0.80, "target": 200},
        "2 hours": {"reduction": 0.60, "target": 180},
        "3 hours": {"reduction": 0.40, "target": 130},
        "4 hours": {"reduction": 0.20, "target": 130},
        "5 hours": {"reduction": 0.00, "target": 130}
    }
    
    selected_time = col2.selectbox("Time passed since last meal bolus:", list(time_options.keys()))
    
    if st.button("Calculate Correction Dose"):
        target = time_options[selected_time]["target"]
        reduction_pct = time_options[selected_time]["reduction"]
        
        if current_bg > target:
            # Step A: Calculate theoretical dose
            # Formula: (Current BG - Target) / Sensitivity
            theoretical_dose = (current_bg - target) / new_sensitivity
            
            # Step B: Apply active insulin reduction
            reduction_value = theoretical_dose * reduction_pct
            final_dose = theoretical_dose - reduction_value
            
            # Display Results
            st.divider()
            st.subheader(f"Recommended Correction: {round(final_dose, 1)} Units")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Theoretical Dose", f"{round(theoretical_dose, 2)} U")
            c2.metric("Active Insulin (IOB)", f"-{int(reduction_pct*100)}%")
            c3.metric("Final Dose", f"{round(final_dose, 1)} U")
            
            st.warning(f"**Explanation:** At {selected_time} post-meal, your target is < {target} mg/dL. Your previous bolus is still approximately {int(reduction_pct*100)}% active, so we subtracted {round(reduction_value, 2)} units to avoid stacking.")
        
        elif current_bg == 0:
            st.error("Please enter a valid glucose reading.")
        else:
            st.success(f"Your blood sugar is {current_bg} mg/dL, which is within the target for {selected_time} (< {target} mg/dL). No correction needed.")

    st.caption("⚠️ Disclaimer: This calculation is based on standard rapid-acting insulin curves (5 hours). Always verify with your doctor.")

# --- SECTION: LOG BLOOD SUGAR ---
elif menu == "🩸 Log Blood Sugar":
    st.title("🩸 Blood Glucose Logger")
    st.write("Keep track of your glucose levels with context-aware safety checks.")

    bg_df = load_bg_data()

    with st.form("bg_form"):
        col1, col2 = st.columns(2)
        bg_value = col1.number_input("Blood Glucose Level (mg/dL)", min_value=0, step=1)
        # We use clinical categories for better logic
        bg_note = col2.selectbox("Moment", ["Fasting / Pre-meal", "Post-meal (2h)", "Bedtime", "Other"])
        
        submitted_bg = st.form_submit_button("Save Reading")
        
        if submitted_bg:
            if bg_value > 0:
                # --- DYNAMIC SECURITY CHECK ---
                is_hypo = bg_value < 70  # Standard clinical threshold
                is_hyper = False
                hyper_message = ""

                # Hyperglycemia logic based on the moment
                if bg_note == "Fasting / Pre-meal":
                    if bg_value > 130:
                        is_hyper = True
                        hyper_message = "Target for fasting is < 130 mg/dL."
                elif bg_note == "Post-meal (2h)":
                    if bg_value > 180:
                        is_hyper = True
                        hyper_message = "Target for post-meal is < 180 mg/dL."
                else: # Bedtime or Other
                    if bg_value > 160: # General safe threshold for other moments
                        is_hyper = True
                        hyper_message = "Reading is above standard safe range."

                # --- ALERTS DISPLAY ---
                if is_hypo:
                    st.error(f"🚨 **HYPOGLYCEMIA DETECTED ({bg_value} mg/dL)**. Follow the 'Rule of 15' immediately and contact your doctor if symptoms persist.")
                elif is_hyper:
                    st.warning(f"⚠️ **HYPERGLYCEMIA DETECTED**. {hyper_message} Drink water and monitor for ketones if levels continue to rise.")
                else:
                    st.success(f"✅ Reading of {bg_value} mg/dL is within your target range for {bg_note.lower()}.")
                
                # Save to CSV
                new_bg = {
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Reading_mgdL": bg_value,
                    "Note": bg_note
                }
                bg_df = pd.concat([bg_df, pd.DataFrame([new_bg])], ignore_index=True)
                bg_df.to_csv(BG_LOG_FILE, index=False)
            else:
                st.error("Please enter a valid reading.")



# --- SECTION 4: HISTORY & CHARTS --- 
elif menu == "📊 My History":
    st.title("📊 Weekly Health Overview")

    st.divider()
    st.subheader("🤖 Gemma AI Health Insight")
    st.write("Let Gemma analyze your weekly patterns and suggest optimizations.")

    # We need the vectorstore for the RAG part
    vectorstore = init_diabetes_ai()

    if st.button("Generate AI Clinical Report"):
        with st.spinner("Gemma is analyzing your glucose patterns..."):
            bg_data = load_bg_data() # Ensure latest data is loaded
            report = analyze_history_with_gemma(meals_df, bg_data, vectorstore)
            
            st.markdown("---")
            st.markdown("### 📋 Clinical Summary")
            st.write(report)
            st.info("💡 Tip: You can discuss this report with your doctor during your next visit.")

    if not meals_df.empty:
        # Data table
        st.dataframe(meals_df.tail(10), use_container_width=True)
        
        # CHO graph
        fig = px.bar(meals_df, x="Date", y="CHO_g", color="Meal", 
                     title="Carbohydrate Intake per Meal", barmode='group')
        st.plotly_chart(fig, use_container_width=True)
        
        # Insulin graph
        fig2 = px.line(meals_df, x="Date", y="Insulin_U", markers=True,
                      title="Insulin Units Administered over Time")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.warning("No data found. Log your first meal in the Calculator section!")

    bg_df = load_bg_data() # Load the BG data here

    # --- TAB: Glucose Trends ---
    st.subheader("📈 Blood Glucose Trends")
    if not bg_df.empty:
        # Create a line chart for Glucose
        fig_bg = px.line(bg_df, x="Date", y="Reading_mgdL", markers=True,
                         title="Blood Sugar Evolution",
                         color_discrete_sequence=["#FF4B4B"])
        
        # Add target range lines (70-180 mg/dL) for medical context
        fig_bg.add_hline(y=70, line_dash="dash", line_color="green", annotation_text="Min Target")
        fig_bg.add_hline(y=180, line_dash="dash", line_color="orange", annotation_text="Max Target Post-meal")
        fig_bg.add_hline(y=130, line_dash="dash", line_color="blue", annotation_text="Max Target Pre-meal")
        
        st.plotly_chart(fig_bg, use_container_width=True)
    else:
        st.info("No glucose readings found. Log your first reading to see the trend.")



 # --- SECTION 5: SAFETY PROTOCOLS ---
elif menu == "🆘 Safety Protocols":
    st.title("🆘 Emergency Protocols")
    st.warning("This section contains general safety guidelines. In case of severe symptoms, call emergency services immediately.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.error("### 📉 Hypoglycemia (Low Sugar)")
        st.markdown("""
        **Symptoms:** Shaking, sweating, hunger, dizziness, confusion.
        
        **Immediate Action (Rule of 15):**
        1. Consume **15g of fast-acting carbs** (e.g., 3 glucose tablets, 1/2 cup of juice, 1 tablespoon of sugar).
        2. Wait **15 minutes**.
        3. Check blood sugar. 
        4. If still below 70 mg/dL, repeat.
        
        **When to contact a doctor:**
        - If you lose consciousness .
        - If hypoglycemia happens frequently without a clear cause.
        """)
        
    with col2:
        st.error("### 📈 Hyperglycemia (High Sugar)")
        st.markdown("""
        **Symptoms:** Excessive thirst, frequent urination, blurred vision, fatigue.
        
        **Immediate Action:**
        1. Drink plenty of **water** (sugar-free).
        2. Check for ketones if blood sugar is above 240 mg/dL.
        3. Administer correction dose as per your medical plan.
        
        **When to contact a doctor:**
        - If blood sugar stays high despite correction doses.
        - If you feel nauseous or your breath smells fruity (Ketosis risk).
        """)