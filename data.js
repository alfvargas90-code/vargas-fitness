// NOTE: SEED_DEXA (BodySpec 2023-10-20) removed 2026-06-01 — KPI tiles now read
// the latest VeSync reading (vesync/snapshot.json + history.json), not the stale
// DEXA seed. The DEXA scan lives in the handoff/spec docs if ever needed again.

// Seeded weight log: just the DEXA-day weight to start
const SEED_WEIGHT = [
  { date: "2023-10-20", weight_lbs: 166.0, note: "DEXA scan day" },
  { date: "2026-04-29", weight_lbs: 173.3, note: "Alfie scale" },
  { date: "2026-05-20", weight_lbs: 168.2, note: "lean reading (ChatGPT handoff)" },
];

// Seeded bioimpedance scale readings (Alfie scale).
// Kept separate from SEED_DEXA so methodologies don't mix on charts.
const SEED_SCALE = [
  {
    date: "2026-04-29",
    source: "Alfie scale",
    weight_lbs: 173.3,
    weight_change_lbs: 1.9,
    bmi: 27.2,
    metabolic_age: 36,
    body_fat_pct: 15.3,
    fat_free_weight_lbs: 146.8,
    subcutaneous_fat_pct: 12.6,
    visceral_fat_rating: 9,        // unitless rating from the scale, NOT lbs
    body_water_pct: 61.0,
    skeletal_muscles_pct: 54.6,
    bone_mass_lbs: 7.3,
    bmr_kcal: 1784,
    muscle_mass_lbs: 139.3,
    protein_pct: 19.2,
    ratings: {
      bmi: "High",
      metabolic_age: "High",
      body_fat_pct: "Fitness",
      subcutaneous_fat_pct: "Standard",
      visceral_fat_rating: "Standard",
      body_water_pct: "Standard",
      skeletal_muscles_pct: "Standard",
      bone_mass_lbs: "Standard",
      bmr_kcal: "Standard",
      muscle_mass_lbs: "Excellent",
      protein_pct: "Excellent",
    },
  },
  {
    date: "2026-05-20",
    source: "Alfie scale (lean reading)",
    weight_lbs: 168.2,
    weight_change_lbs: -5.1,
    body_fat_pct: 14.7,
    muscle_mass_lbs: 136.2,
    skeletal_muscles_pct: 55.0,
    body_water_pct: 61.5,
    bmr_kcal: 1772,
    // partial reading from ChatGPT handoff — bmi/metabolic_age/etc. not captured
    ratings: {
      body_fat_pct: "Fitness",
      muscle_mass_lbs: "Excellent",
      skeletal_muscles_pct: "Standard",
      body_water_pct: "Standard",
    },
  },
];

const SEED_GOALS = {
  target_weight_lbs: 160,
  target_body_fat_pct: 15,
  target_date: "2026-12-31",
};

// Body fat percentile reference for men (from the BodySpec report)
const BF_PERCENTILES_MEN = [
  { age: "20-29", p20: 16, p40: 20, p60: 24, p80: 27 },
  { age: "30-39", p20: 18, p40: 22, p60: 26, p80: 30 },
  { age: "40-49", p20: 20, p40: 24, p60: 27, p80: 31 },
  { age: "50-59", p20: 21, p40: 25, p60: 29, p80: 33 },
  { age: ">60",   p20: 21, p40: 25, p60: 30, p80: 33 },
];

// ============================================================
//  TRAINING / RECOVERY / ACTIVITY / NUTRITION
//  Sourced from Polar data export + ChatGPT handoff (2026-05-20)
// ============================================================

// Polar device profile baselines
const SEED_PROFILE = {
  sex: "Male",
  dob: "1990-08-30",
  height_cm: 170,
  height_in: 67,
  profile_weight_kg: 77,
  profile_weight_lbs: 169.7,
  max_hr: 190,
  resting_hr: 55,
  sleep_goal_h: 7,
};

// HR zones derived from Max HR 190 (standard %max bands)
const HR_ZONES = [
  { zone: "Z1 Recovery",   pct: "50–60%", lo: 95,  hi: 114 },
  { zone: "Z2 Endurance",  pct: "60–70%", lo: 114, hi: 133 },
  { zone: "Z3 Tempo",      pct: "70–80%", lo: 133, hi: 152 },
  { zone: "Z4 Threshold",  pct: "80–90%", lo: 152, hi: 171 },
  { zone: "Z5 VO2 max",    pct: "90–100%",lo: 171, hi: 190 },
];

// Weekly activity averages (Polar)
const SEED_ACTIVITY = {
  steps_per_day: 9900,
  miles_per_week: 23.5,
  activity_completion_pct: 115,
  active_day_burn_kcal: [2900, 3200],
  tdee_kcal: [2500, 2900],
};

// Training load pattern — the observed overreaching cycle
const SEED_TRAINING = {
  pattern: [
    { day: "D1", load: "High",          score: 3 },
    { day: "D2", load: "High",          score: 3 },
    { day: "D3", load: "High",          score: 3 },
    { day: "D4", load: "Mod-High",      score: 2.5 },
    { day: "D5", load: "Moderate",      score: 2 },
    { day: "D6", load: "Low",           score: 1 },
    { day: "D7", load: "Low",           score: 1 },
    { day: "D8", load: "High re-spike", score: 3 },
  ],
  conclusion: "Temporarily overreaching — intensity clustering + insufficient low-stress days, with a calorie deficit overlapping high output. NOT overtrained, NOT undertraining.",
  target_structure: "2–3 high · 2–3 moderate · 1–2 recovery/light days per week. Stop clustering intensity.",
};

// Recovery (ANS / HRV) state profile
const SEED_RECOVERY = {
  good_day:        { ans_charge: "+5 to +10", hrv: "above baseline", hr: "lower resting HR" },
  compromised_day: { ans_charge: "negative",  hrv: "suppressed",     hr: "slightly elevated" },
  causes: ["caloric deficit", "accumulated load", "insufficient recovery spacing", "sleep inconsistency", "glycogen depletion"],
};

// Nutrition targets + meal-prep batches
const SEED_NUTRITION = {
  training_day: { kcal: "2200–2500", protein_g: "180–200", carbs_g: "150–220", fat_g: "55–70" },
  recovery_day: { kcal: "2000–2200", protein_g: "180+",    carbs_g: "lower/mod", fat_g: "moderate" },
  keep:   ["chicken + rice bowls", "cottage cheese", "Fairlife shakes", "high-protein consistency"],
  reduce: ["sausage stacking", "cheese stacking", "stacked high-fat meals (eggs/sausage/cheese/cream cheese)"],
  note: "Fat isn't the enemy — the issue is cumulative calorie density from high-fat stacking + under-fueling carbs around training.",
};

const SEED_MEALPREP = [
  { name: "Mar1 (locked)",                kcal: 778, protein_g: 60,   fat_g: 55,   carbs_g: 10 },
  { name: "Batch 316 (locked)",           kcal: 760, protein_g: 61,   fat_g: 51.5, carbs_g: 7.5 },
  { name: "Chicken prep — 240g/meal (×4)", kcal: 280, protein_g: 45,   fat_g: 7,    carbs_g: 8 },
];

const PHYSIQUE_PROJECTION = [
  { window: "1–2 weeks", outcome: "Visibly tighter, reduced water retention" },
  { window: "3–5 weeks", outcome: "Upper abs increasingly visible" },
  { window: "6–8 weeks", outcome: "Clear lean athletic look — no crash dieting" },
];
