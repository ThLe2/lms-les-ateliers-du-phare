/* ---------------------------------------------------------------
   Configuration du centre — écrite par l'installateur Accompagna.
   La clé publique (anon) est faite pour être publiée : ce sont les
   politiques RLS qui protègent les données. NE JAMAIS mettre ici
   une clé secrète (service_role), elle contourne toutes les règles.
   --------------------------------------------------------------- */
window.LMS_CONFIG = {
    "SUPABASE_URL":  "https://fnhnumzosdehvbotnswh.supabase.co",
    "SUPABASE_ANON_KEY":  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZuaG51bXpvc2RlaHZib3Ruc3doIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ2MTg3MTUsImV4cCI6MjExMDE5NDcxNX0.wN7S3xVcVapTgPIqqYBcinb35Bqf16IuY1nf_eufu8g",
    "ADRESSE_SITE":  "essai.accompagna.fr",
    "CENTRE":  {
                   "nom":  "Les Ateliers du Phare",
                   "logo":  "logo.svg",
                   "couleur":  "#1d4e89"
               }
};