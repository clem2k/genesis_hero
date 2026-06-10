#include <genesis.h>
#include "game.h"
#include "resources.h"
#include "song_data.h"

// ─────────────────────────────────────────────────────────────────────────────
// GLOBAL STATE
// ─────────────────────────────────────────────────────────────────────────────

u16 game_state = STATE_TITLE;
GameScore game_score;
ActiveNote active_notes[MAX_ACTIVE_NOTES];
Sprite* note_sprites[MAX_ACTIVE_NOTES];
Sprite* hitzone_sprites[NUM_LANES];

// Explosion pool
ActiveExplosion explosions[MAX_EXPLOSIONS];
Sprite* explosion_sprites[MAX_EXPLOSIONS];

// Selection state
u16 selected_song_idx = 0;
u16 selected_difficulty = DIFFICULTY_NORMAL;

// Gameplay state
u16 gameplay_phase = PHASE_COUNTDOWN;
Sprite* countdown_sprite = NULL;
u32 current_frame = 0;
u16 next_spawn_idx = 0;
u16 total_notes_in_song = 0;
u16 notes_cleared_count = 0;
u16 active_note_count = 0;
const u16 (*song_notes_ptr)[][2] = NULL;
const u8* active_lanes_ptr = NULL;
u8 active_lane_count = 0;
u32 base_note_value = 1000;

// High score system (SRAM)
#define SRAM_MAGIC 0x47484552 // "GHER" (Genesis Hero)
#define LEADERBOARD_LIMIT 5
u32 high_scores[SONG_COUNT][DIFFICULTY_COUNT];
u32 leaderboards[SONG_COUNT][DIFFICULTY_COUNT][LEADERBOARD_LIMIT];

// Post game menu state
u16 selected_post_option = 0;
bool post_menu_dirty = TRUE;

// Feedback flash timer (per lane)
u8 hitzone_flash_timer[NUM_LANES];

// Combo strobe effect
u16 combo_strobe_frame = 0;

// Input tracking
u16 last_joy_state = 0;

// Palettes
u16 palette_title[16];
u16 palette_gameplay[16];

// Lane X positions: 5 lanes of 32px centered on 320px screen
// Total track width = 5 * 32 = 160px, centered -> starts at X=80
// Lane centers: 80+16=96, 112+16=128, 144+16=160, 176+16=192, 208+16=224
// But sprite position is top-left corner, so subtract 16 to center 32px sprite
const s16 lane_x_coords[NUM_LANES] = {
    80,   // Lane 0: LEFT
    112,  // Lane 1: UP
    144,  // Lane 2: DOWN
    176,  // Lane 3: A
    208   // Lane 4: B
};

// Dynamic Lane X positions based on current difficulty (centered tracks)
s16 play_lane_x[NUM_LANES];

// Lane label strings for display
const char* lane_labels[NUM_LANES] = {
    "L", "U", "D", "A", "B"
};

// Colors for HUD lane indicators (Genesis 9-bit: 0x0BGR)
const u16 lane_colors[NUM_LANES] = {
    0x00E0, // Lane 0: Green (LEFT)
    0x0E00, // Lane 1: Blue (UP)
    0x00EE, // Lane 2: Yellow (DOWN)
    0x000E, // Lane 3: Red (A)
    0x0E0E  // Lane 4: Purple (B)
};

// Forward declarations
void enterTitle(void);
void enterSelect(void);
void enterPlay(void);
void enterResults(void);
void enterLeaderboard(void);
void updateLeaderboard(void);
void enterPostMenu(void);
void updatePostMenu(void);
void drawProgressBar(void);
void updateTitle(void);
void updateSelect(void);
void updatePlay(void);
void updateResults(void);
void drawHUD(void);
void spawnNote(u16 note_idx);
void updateActiveNotes(void);
void checkNoteHit(u8 lane);
void spawnExplosion(s16 x, s16 y);
void updateExplosions(void);
void drawFeedbackText(const char* text, u8 x, u8 y);
void joyHandler(u16 joy, u16 changed, u16 state);

void loadSaveData() {
    SRAM_enable();
    u32 magic = SRAM_readLong(0);
    if (magic == SRAM_MAGIC) {
        for (u16 s = 0; s < SONG_COUNT; s++) {
            for (u16 d = 0; d < DIFFICULTY_COUNT; d++) {
                for (u16 i = 0; i < LEADERBOARD_LIMIT; i++) {
                    u32 offset = 4 + (s * DIFFICULTY_COUNT * LEADERBOARD_LIMIT + d * LEADERBOARD_LIMIT + i) * 4;
                    leaderboards[s][d][i] = SRAM_readLong(offset);
                }
            }
        }
        // Update high_scores for backward compatibility / song selection screen
        for (u16 s = 0; s < SONG_COUNT; s++) {
            for (u16 d = 0; d < DIFFICULTY_COUNT; d++) {
                high_scores[s][d] = leaderboards[s][d][0];
            }
        }
    } else {
        // Initialize
        for (u16 s = 0; s < SONG_COUNT; s++) {
            for (u16 d = 0; d < DIFFICULTY_COUNT; d++) {
                for (u16 i = 0; i < LEADERBOARD_LIMIT; i++) {
                    leaderboards[s][d][i] = 0;
                }
                high_scores[s][d] = 0;
            }
        }
        SRAM_writeLong(0, SRAM_MAGIC);
        for (u16 s = 0; s < SONG_COUNT; s++) {
            for (u16 d = 0; d < DIFFICULTY_COUNT; d++) {
                for (u16 i = 0; i < LEADERBOARD_LIMIT; i++) {
                    u32 offset = 4 + (s * DIFFICULTY_COUNT * LEADERBOARD_LIMIT + d * LEADERBOARD_LIMIT + i) * 4;
                    SRAM_writeLong(offset, 0);
                }
            }
        }
    }
    SRAM_disable();
}

s16 saveLeaderboardScore(u16 song_idx, u16 diff, u32 score) {
    if (score == 0) return -1; // don't save 0 scores
    
    s16 insert_pos = -1;
    
    // Find insertion position
    for (s16 i = 0; i < LEADERBOARD_LIMIT; i++) {
        if (score > leaderboards[song_idx][diff][i]) {
            insert_pos = i;
            break;
        }
    }
    
    if (insert_pos != -1) {
        SRAM_enable();
        // Shift existing scores down
        for (s16 i = LEADERBOARD_LIMIT - 1; i > insert_pos; i--) {
            leaderboards[song_idx][diff][i] = leaderboards[song_idx][diff][i - 1];
            u32 offset = 4 + (song_idx * DIFFICULTY_COUNT * LEADERBOARD_LIMIT + diff * LEADERBOARD_LIMIT + i) * 4;
            SRAM_writeLong(offset, leaderboards[song_idx][diff][i]);
        }
        
        // Insert new score
        leaderboards[song_idx][diff][insert_pos] = score;
        u32 offset = 4 + (song_idx * DIFFICULTY_COUNT * LEADERBOARD_LIMIT + diff * LEADERBOARD_LIMIT + insert_pos) * 4;
        SRAM_writeLong(offset, score);
        SRAM_disable();
        
        // Update high_scores cache
        high_scores[song_idx][diff] = leaderboards[song_idx][diff][0];
    }
    
    return insert_pos; // returns 0-4 for rank 1-5, or -1 if not qualified
}

u16 getGlobalMultiplier() {
    u16 mult = 1;
    if (game_score.combo >= 30) mult = 5;
    else if (game_score.combo >= 20) mult = 4;
    else if (game_score.combo >= 10) mult = 2;
    
    if (game_score.combo_active) {
        mult *= 2;
    }
    return mult;
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────────────────────

void registerSFX() {
    XGM_setPCM(SFX_1_ID, sfx_1, sizeof(sfx_1));
    XGM_setPCM(SFX_2_ID, sfx_2, sizeof(sfx_2));
    XGM_setPCM(SFX_3_ID, sfx_3, sizeof(sfx_3));
    XGM_setPCM(SFX_INTRO_ID, sfx_intro, sizeof(sfx_intro));
    XGM_setPCM(SFX_SCORE_0_ID, sfx_score_0, sizeof(sfx_score_0));
    XGM_setPCM(SFX_SCORE_1000_ID, sfx_score_1000, sizeof(sfx_score_1000));
    XGM_setPCM(SFX_SCORE_200K_ID, sfx_score_200k, sizeof(sfx_score_200k));
    XGM_setPCM(SFX_SCORE_600K_ID, sfx_score_600k, sizeof(sfx_score_600k));
    XGM_setPCM(SFX_SCORE_900K_ID, sfx_score_900k, sizeof(sfx_score_900k));
}

int main() {
    SYS_disableInts();
    VDP_setScreenWidth320();
    VDP_setScreenHeight224();
    VDP_setTextPriority(TRUE);
    SPR_init();
    SYS_enableInts();

    JOY_init();
    JOY_setEventHandler(joyHandler);
    loadSaveData();

    registerSFX();
    XGM_startPlayPCM(SFX_INTRO_ID, 15, SOUND_PCM_CH2);

    enterTitle();

    while (1) {
        switch (game_state) {
            case STATE_TITLE:
                updateTitle();
                break;
            case STATE_SELECT:
                updateSelect();
                break;
            case STATE_PLAY:
                updatePlay();
                break;
            case STATE_RESULTS:
                updateResults();
                break;
            case STATE_LEADERBOARD:
                updateLeaderboard();
                break;
            case STATE_POST_MENU:
                updatePostMenu();
                break;
        }

        SPR_update();
        SYS_doVBlankProcess();
    }

    return 0;
}

// ─────────────────────────────────────────────────────────────────────────────
// STATE TRANSITIONS
// ─────────────────────────────────────────────────────────────────────────────

void enterTitle() {
    game_state = STATE_TITLE;

    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    SPR_reset();

    // Draw Title Background
    VDP_drawImageEx(BG_B, &bg_title, TILE_ATTR_FULL(PAL0, FALSE, FALSE, FALSE, TILE_USER_INDEX), 0, 0, TRUE, CPU);
    PAL_setPalette(PAL0, bg_title.palette->data, DMA);
    PAL_setColor(15, 0x0EEE); // White text

    // Title text overlay
    VDP_drawText("GENESIS HERO", 14, 10);
    VDP_drawText("PRESS START", 14, 16);

    current_frame = 0;
}

void enterSelect() {
    game_state = STATE_SELECT;

    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    SPR_reset();

    // Dark purple-black background
    PAL_setColor(0, 0x0112);

    // White text
    PAL_setColor(15, 0x0EEE);

    VDP_drawText("= SELECT SONG =", 12, 2);
    VDP_drawText("UP/DOWN: SONG", 4, 24);
    VDP_drawText("LEFT/RIGHT: DIFFICULTY", 4, 25);
    VDP_drawText("PRESS START TO ROCK!", 10, 27);

    current_frame = 0;
}

void enterPlay() {
    game_state = STATE_PLAY;

    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    SPR_reset();

    // Clear active notes pool
    for (u16 i = 0; i < MAX_ACTIVE_NOTES; i++) {
        active_notes[i].active = FALSE;
        active_notes[i].hit = FALSE;
        note_sprites[i] = NULL;
    }

    // Clear explosion pool
    for (u16 i = 0; i < MAX_EXPLOSIONS; i++) {
        explosions[i].active = FALSE;
        explosion_sprites[i] = NULL;
    }

    // Clear hitzone flash timers
    for (u16 i = 0; i < NUM_LANES; i++) {
        hitzone_flash_timer[i] = 0;
    }

    // Reset score
    game_score.score = 0;
    game_score.combo = 0;
    game_score.max_combo = 0;
    game_score.perfect_count = 0;
    game_score.good_count = 0;
    game_score.miss_count = 0;
    game_score.combo_gauge = 0;
    game_score.combo_active = FALSE;
    game_score.combo_timer = 0;

    gameplay_phase = PHASE_COUNTDOWN;

    // Load active song metadata
    const SongData* song = &songs[selected_song_idx];
    total_notes_in_song = song->note_counts[selected_difficulty];
    song_notes_ptr = (const u16(*)[][2])song->notes[selected_difficulty];
    active_lanes_ptr = song->active_lanes[selected_difficulty];
    active_lane_count = song->lane_counts[selected_difficulty];
    base_note_value = total_notes_in_song > 0 ? (1000000 / total_notes_in_song) : 1000;

    current_frame = 0;
    next_spawn_idx = 0;
    notes_cleared_count = 0;
    active_note_count = 0;
    combo_strobe_frame = 0;

    // Initialize play_lane_x dynamically for centered tracks
    for (u16 i = 0; i < NUM_LANES; i++) {
        play_lane_x[i] = 0;
    }
    for (u16 i = 0; i < active_lane_count; i++) {
        u8 lane = active_lanes_ptr[i];
        s16 track_width = active_lane_count * 32;
        s16 start_x = (320 - track_width) / 2;
        play_lane_x[lane] = start_x + (i * 32);
    }

    // Select difficulty-specific background
    const Image* bg_img = &bg_gameplay_normal;
    if (selected_difficulty == DIFFICULTY_EASY) {
        bg_img = &bg_gameplay_easy;
    } else if (selected_difficulty == DIFFICULTY_HARD) {
        bg_img = &bg_gameplay_hard;
    }

    // Draw Gameplay Background
    VDP_drawImageEx(BG_B, bg_img, TILE_ATTR_FULL(PAL0, FALSE, FALSE, FALSE, TILE_USER_INDEX), 0, 0, TRUE, CPU);
    PAL_setPalette(PAL0, bg_img->palette->data, DMA);
    PAL_setColor(15, 0x0EEE); // White text

    // PAL1: Note sprite colors (set up per-lane coloring is handled by sprite frames)
    // The note sprites use their own embedded palette from rescomp
    PAL_setPalette(PAL1, spr_note.palette->data, DMA);

    // PAL2: Hitzone sprites
    PAL_setPalette(PAL2, spr_hitzone.palette->data, DMA);

    // PAL3: Countdown sprites (loaded initially, switched to explosion when gameplay starts)
    PAL_setPalette(PAL3, spr_countdown.palette->data, DMA);

    // Spawn Hitzone Sprites at the bottom
    for (u16 i = 0; i < NUM_LANES; i++) {
        bool lane_active = FALSE;
        for (u16 l = 0; l < active_lane_count; l++) {
            if (active_lanes_ptr[l] == i) {
                lane_active = TRUE;
                break;
            }
        }

        if (lane_active) {
            hitzone_sprites[i] = SPR_addSprite(&spr_hitzone, play_lane_x[i], HIT_ZONE_Y, TILE_ATTR(PAL2, TRUE, FALSE, FALSE));
            SPR_setAnimAndFrame(hitzone_sprites[i], 0, 0);
        } else {
            hitzone_sprites[i] = NULL;
        }
    }

    // Spawn Countdown Sprite (hidden initially)
    countdown_sprite = SPR_addSprite(&spr_countdown, 128, 80, TILE_ATTR(PAL3, TRUE, FALSE, FALSE));
    if (countdown_sprite != NULL) {
        SPR_setVisibility(countdown_sprite, HIDDEN);
    }

    // Draw song title (Left) and artist (Right) on Row 0
    VDP_drawText(song->name, 0, 0);
    VDP_drawText(song->artist, 40 - strlen(song->artist), 0);

    drawHUD();
}

void enterResults() {
    game_state = STATE_RESULTS;

    XGM_stopPlay();

    s16 leaderboard_rank = saveLeaderboardScore(selected_song_idx, selected_difficulty, game_score.score);
    bool is_new_high = (leaderboard_rank == 0); // Rank 1 is new highest score!

    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    SPR_reset();

    // Dark stage background
    PAL_setColor(0, 0x0113);
    PAL_setColor(15, 0x0EEE); // White text

    VDP_drawText("= RESULTS =", 14, 2);
    VDP_drawText("========================", 8, 4);

    if (is_new_high) {
        VDP_drawText("NEW HIGH SCORE!", 12, 5);
    } else if (leaderboard_rank != -1) {
        char rank_str[32];
        sprintf(rank_str, "RANKED #%d ON LEADERBOARD!", leaderboard_rank + 1);
        VDP_drawText(rank_str, 8, 5);
    }

    current_frame = 0;

    // Play tiered results score SFX
    u32 final_score = game_score.score;
    u8 sfx_id = SFX_SCORE_0_ID;

    if (final_score >= 900000) {
        sfx_id = SFX_SCORE_900K_ID;
    } else if (final_score >= 600000) {
        sfx_id = SFX_SCORE_600K_ID;
    } else if (final_score >= 200000) {
        sfx_id = SFX_SCORE_200K_ID;
    } else if (final_score >= 1000) {
        sfx_id = SFX_SCORE_1000_ID;
    } else {
        sfx_id = SFX_SCORE_0_ID;
    }

    XGM_startPlayPCM(sfx_id, 15, SOUND_PCM_CH2);
}

// ─────────────────────────────────────────────────────────────────────────────
// STATE UPDATES
// ─────────────────────────────────────────────────────────────────────────────

void updateTitle() {
    current_frame++;

    // Blinking "PRESS START" text
    if ((current_frame / 25) % 2 == 0) {
        VDP_drawText("PRESS START", 14, 16);
    } else {
        VDP_clearText(14, 16, 11);
    }
}

void updateSelect() {
    char song_text[40];
    char artist_text[40];
    char diff_text[30];
    char high_score_text[32];

    // Clear previous song info area
    VDP_clearText(2, 7, 36);
    VDP_clearText(2, 8, 36);
    VDP_clearText(2, 9, 36);
    VDP_clearText(2, 10, 36);
    VDP_clearText(2, 12, 36);
    VDP_clearText(2, 14, 36);
    VDP_clearText(2, 16, 36);

    const SongData* song = &songs[selected_song_idx];

    sprintf(song_text, "SONG: %s", song->name);
    VDP_drawText(song_text, 4, 7);

    sprintf(artist_text, "BY:   %s", song->artist);
    VDP_drawText(artist_text, 4, 9);

    switch (selected_difficulty) {
        case DIFFICULTY_EASY:
            sprintf(diff_text, "DIFFICULTY: * EASY *");
            break;
        case DIFFICULTY_NORMAL:
            sprintf(diff_text, "DIFFICULTY: ** NORMAL **");
            break;
        case DIFFICULTY_HARD:
            sprintf(diff_text, "DIFFICULTY: *** HARD ***");
            break;
    }
    VDP_drawText(diff_text, 4, 12);

    // Draw lane preview for selected difficulty
    char lanes_str[30];
    u8 lc = song->lane_counts[selected_difficulty];
    sprintf(lanes_str, "LANES: %d", lc);
    VDP_drawText(lanes_str, 4, 14);

    sprintf(high_score_text, "HIGH SCORE: %lu", high_scores[selected_song_idx][selected_difficulty]);
    VDP_drawText(high_score_text, 4, 16);
}

void drawProgressBar() {
    if (gameplay_phase != PHASE_PLAYING) return;

    const SongData* song = &songs[selected_song_idx];
    u32 total_frames = (u32)song->duration * 60;
    if (total_frames == 0) total_frames = 1;

    u32 frame = current_frame;
    if (frame > total_frames) frame = total_frames;

    char bar[32];
    strcpy(bar, "[");
    u16 progress_width = 20;
    u32 filled = (frame * progress_width) / total_frames;
    for (u16 i = 0; i < progress_width; i++) {
        if (i < filled) strcat(bar, "#");
        else strcat(bar, "-");
    }
    strcat(bar, "]");

    // Draw at column 10, row 27
    VDP_drawText(bar, 10, 27);
}

void updatePlay() {
    if (gameplay_phase == PHASE_COUNTDOWN) {
        current_frame++;

        // 3 -> 2 -> 1 -> GO count down
        // 60 frames per count (1 second)
        // Show for 40 frames, hide for 20 frames
        if (current_frame == 1) {
            if (countdown_sprite != NULL) {
                SPR_setAnimAndFrame(countdown_sprite, 0, 0); // "3"
                SPR_setVisibility(countdown_sprite, VISIBLE);
            }
            XGM_startPlayPCM(SFX_3_ID, 15, SOUND_PCM_CH2);
        }
        else if (current_frame == 41) {
            if (countdown_sprite != NULL) {
                SPR_setVisibility(countdown_sprite, HIDDEN);
            }
        }
        else if (current_frame == 61) {
            if (countdown_sprite != NULL) {
                SPR_setAnimAndFrame(countdown_sprite, 0, 1); // "2"
                SPR_setVisibility(countdown_sprite, VISIBLE);
            }
            XGM_startPlayPCM(SFX_2_ID, 15, SOUND_PCM_CH2);
        }
        else if (current_frame == 101) {
            if (countdown_sprite != NULL) {
                SPR_setVisibility(countdown_sprite, HIDDEN);
            }
        }
        else if (current_frame == 121) {
            if (countdown_sprite != NULL) {
                SPR_setAnimAndFrame(countdown_sprite, 0, 2); // "1"
                SPR_setVisibility(countdown_sprite, VISIBLE);
            }
            XGM_startPlayPCM(SFX_1_ID, 15, SOUND_PCM_CH2);
        }
        else if (current_frame == 161) {
            if (countdown_sprite != NULL) {
                SPR_setVisibility(countdown_sprite, HIDDEN);
            }
        }
        else if (current_frame == 181) {
            if (countdown_sprite != NULL) {
                SPR_setAnimAndFrame(countdown_sprite, 0, 3); // "GO"
                SPR_setVisibility(countdown_sprite, VISIBLE);
            }
        }
        else if (current_frame == 221) {
            if (countdown_sprite != NULL) {
                SPR_setVisibility(countdown_sprite, HIDDEN);
            }
        }
        else if (current_frame == 241) {
            // Clean up countdown sprite
            if (countdown_sprite != NULL) {
                SPR_releaseSprite(countdown_sprite);
                countdown_sprite = NULL;
            }

            // Restore PAL3 to explosion palette
            PAL_setPalette(PAL3, spr_explosion.palette->data, DMA);

            // Start music playback
            const SongData* song = &songs[selected_song_idx];
            XGM_startPlay(song->music);

            // Transition phase
            gameplay_phase = PHASE_PLAYING;
            current_frame = 0; // reset frame counter to sync with note charts
        }

        // Keep updating hitzones (for empty button presses feedback during countdown)
        for (u16 i = 0; i < NUM_LANES; i++) {
            if (hitzone_flash_timer[i] > 0) {
                hitzone_flash_timer[i]--;
                if (hitzone_flash_timer[i] == 0 && hitzone_sprites[i] != NULL) {
                    SPR_setAnimAndFrame(hitzone_sprites[i], 0, 0);
                }
            }
        }
        return;
    }

    current_frame++;
    drawProgressBar();

    // 1. Spawning Notes
    u32 lead_in_frames = (HIT_ZONE_Y + 32) / NOTE_SPEED;  // Account for 32px spawn above screen

    while (next_spawn_idx < total_notes_in_song) {
        u16 note_frame = (*song_notes_ptr)[next_spawn_idx][0];
        if (current_frame + lead_in_frames >= note_frame && note_frame >= current_frame) {
            spawnNote(next_spawn_idx);
            next_spawn_idx++;
        } else if (note_frame < current_frame) {
            // Missed spawn window entirely
            next_spawn_idx++;
        } else {
            break;
        }
    }

    // 2. Move active notes & detect misses
    updateActiveNotes();

    // 3. Update explosions
    updateExplosions();

    // 4. Update hitzone flash timers (auto-revert to idle frame)
    for (u16 i = 0; i < NUM_LANES; i++) {
        if (hitzone_flash_timer[i] > 0) {
            hitzone_flash_timer[i]--;
            if (hitzone_flash_timer[i] == 0 && hitzone_sprites[i] != NULL) {
                SPR_setAnimAndFrame(hitzone_sprites[i], 0, 0);
            }
        }
    }

    // 5. Combo visual strobe effect
    if (game_score.combo_active) {
        combo_strobe_frame++;
        if ((combo_strobe_frame / 4) % 2 == 0) {
            VDP_drawText("BOOST!", 34, 3);
        } else {
            VDP_clearText(34, 3, 6);
        }
    } else {
        if (combo_strobe_frame > 0) {
            VDP_clearText(34, 3, 6);
            combo_strobe_frame = 0;
            drawHUD();
        }
    }

    // 6. Check for song end
    if (notes_cleared_count >= total_notes_in_song && active_note_count == 0) {
        enterResults();
    }
}

void updateResults() {
    char temp[40];

    sprintf(temp, "FINAL SCORE: %lu", game_score.score);
    VDP_drawText(temp, 4, 7);

    sprintf(temp, "MAX COMBO:   %u", game_score.max_combo);
    VDP_drawText(temp, 4, 9);

    sprintf(temp, "PERFECT: %u", game_score.perfect_count);
    VDP_drawText(temp, 4, 12);

    sprintf(temp, "GOOD:    %u", game_score.good_count);
    VDP_drawText(temp, 4, 14);

    sprintf(temp, "MISS:    %u", game_score.miss_count);
    VDP_drawText(temp, 4, 16);

    // Accuracy and rank
    u32 total_hits = game_score.perfect_count + game_score.good_count;
    u32 total_notes = total_notes_in_song > 0 ? total_notes_in_song : 1;
    u32 accuracy = (total_hits * 100) / total_notes;

    char rank = 'F';
    if (accuracy >= 95) rank = 'S';
    else if (accuracy >= 85) rank = 'A';
    else if (accuracy >= 70) rank = 'B';
    else if (accuracy >= 50) rank = 'C';
    else rank = 'D';

    sprintf(temp, "ACCURACY: %lu%%  RANK: %c", accuracy, rank);
    VDP_drawText(temp, 4, 19);

    VDP_drawText("PRESS START TO CONTINUE", 9, 24);
}

void enterLeaderboard() {
    game_state = STATE_LEADERBOARD;

    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    SPR_reset();

    // Dark stage background
    PAL_setColor(0, 0x0113);
    PAL_setColor(15, 0x0EEE); // White text

    VDP_drawText("= LEADERBOARD =", 12, 2);
    VDP_drawText("========================", 8, 4);

    const SongData* song = &songs[selected_song_idx];
    char temp[40];
    sprintf(temp, "SONG: %s", song->name);
    VDP_drawText(temp, 4, 6);

    switch (selected_difficulty) {
        case DIFFICULTY_EASY:   VDP_drawText("DIFFICULTY: EASY", 4, 8); break;
        case DIFFICULTY_NORMAL: VDP_drawText("DIFFICULTY: NORMAL", 4, 8); break;
        case DIFFICULTY_HARD:   VDP_drawText("DIFFICULTY: HARD", 4, 8); break;
    }

    // Display top 5 scores
    for (u16 i = 0; i < LEADERBOARD_LIMIT; i++) {
        u32 score = leaderboards[selected_song_idx][selected_difficulty][i];
        if (score > 0) {
            sprintf(temp, "%d. %08lu", i + 1, score);
        } else {
            sprintf(temp, "%d. --------", i + 1);
        }
        VDP_drawText(temp, 12, 11 + (i * 2));
    }

    VDP_drawText("PRESS START TO CONTINUE", 9, 22);
}

void updateLeaderboard() {
    // Nothing to update continuously
}

void enterPostMenu() {
    game_state = STATE_POST_MENU;
    selected_post_option = 0;
    post_menu_dirty = TRUE;

    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    SPR_reset();

    PAL_setColor(0, 0x0112);
    PAL_setColor(15, 0x0EEE); // White text

    VDP_drawText("= GAME OVER =", 13, 4);
    VDP_drawText("========================", 8, 6);
}

void updatePostMenu() {
    if (!post_menu_dirty) return;
    post_menu_dirty = FALSE;

    // Redraw menu items
    VDP_clearText(8, 10, 24);
    VDP_clearText(8, 12, 24);
    VDP_clearText(8, 14, 24);

    if (selected_post_option == 0) {
        VDP_drawText("> RESTART SONG", 10, 10);
    } else {
        VDP_drawText("  RESTART SONG", 10, 10);
    }

    if (selected_post_option == 1) {
        VDP_drawText("> SONG SELECT", 10, 12);
    } else {
        VDP_drawText("  SONG SELECT", 10, 12);
    }

    if (selected_post_option == 2) {
        VDP_drawText("> TITLE SCREEN", 10, 14);
    } else {
        VDP_drawText("  TITLE SCREEN", 10, 14);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// GAMEPLAY MECHANICS
// ─────────────────────────────────────────────────────────────────────────────

void drawHUD() {
    char score_str[20];
    char mult_str[16];
    char gauge_str[16];

    // Score on Row 1, Left
    sprintf(score_str, "SCORE:%08lu", game_score.score);
    VDP_drawText(score_str, 0, 1);

    // Multiplier on Row 1, Center
    sprintf(mult_str, "MULT:x%-3u", getGlobalMultiplier());
    VDP_drawText(mult_str, 16, 1);

    // Combo gauge bar on Row 1, Right
    s16 gauge_bars = game_score.combo_gauge / 20;  // 0 to 5 bars
    sprintf(gauge_str, "PWR:[");
    for (u16 i = 0; i < 5; i++) {
        if (i < gauge_bars) strcat(gauge_str, "#");
        else strcat(gauge_str, ".");
    }
    strcat(gauge_str, "]");
    VDP_drawText(gauge_str, 32, 1);
}

void spawnNote(u16 note_idx) {
    for (u16 i = 0; i < MAX_ACTIVE_NOTES; i++) {
        if (!active_notes[i].active) {
            u8 lane = (*song_notes_ptr)[note_idx][1];

            // Clamp lane to valid range
            if (lane >= NUM_LANES) return;

            bool is_gold = (note_idx % 6) == 0;

            active_notes[i].active = TRUE;
            active_notes[i].hit = FALSE;
            active_notes[i].note_idx = note_idx;
            active_notes[i].lane = lane;
            active_notes[i].y = SPAWN_Y;
            active_notes[i].gold = is_gold;

            // Add 32x32 note sprite
            note_sprites[i] = SPR_addSprite(&spr_note, play_lane_x[lane], SPAWN_Y, TILE_ATTR(PAL1, TRUE, FALSE, FALSE));
            if (note_sprites[i] != NULL) {
                if (is_gold) {
                    SPR_setAnimAndFrame(note_sprites[i], 0, 5); // 6th frame is Gold
                } else {
                    SPR_setAnimAndFrame(note_sprites[i], 0, lane);
                }
                SPR_setVisibility(note_sprites[i], VISIBLE);
            }

            active_note_count++;
            return;
        }
    }
}

void updateActiveNotes() {
    for (u16 i = 0; i < MAX_ACTIVE_NOTES; i++) {
        if (active_notes[i].active) {
            active_notes[i].y += NOTE_SPEED;

            // Check if note passed the hit window (missed)
            if (active_notes[i].y > HIT_ZONE_Y + (HIT_WINDOW_GOOD * NOTE_SPEED)) {
                if (!active_notes[i].hit) {
                    game_score.miss_count++;
                    game_score.combo = 0;

                    // "MISS" feedback
                    VDP_drawText("MISS!   ", 1, 27);

                    if (game_score.combo_active) {
                        game_score.combo_timer--;
                        game_score.combo_gauge = game_score.combo_timer * 10;
                        if (game_score.combo_timer == 0) {
                            game_score.combo_active = FALSE;
                        }
                    }

                    drawHUD();
                }

                // Remove sprite
                if (note_sprites[i] != NULL) {
                    SPR_releaseSprite(note_sprites[i]);
                    note_sprites[i] = NULL;
                }
                active_notes[i].active = FALSE;
                active_note_count--;
                notes_cleared_count++;
            } else {
                // Update sprite position
                if (note_sprites[i] != NULL && !active_notes[i].hit) {
                    SPR_setPosition(note_sprites[i], play_lane_x[active_notes[i].lane], active_notes[i].y);
                }
            }
        }
    }
}

void checkNoteHit(u8 lane) {
    s16 closest_idx = -1;
    s16 min_y_diff = 999;

    // Find closest active note in this lane to the hit zone
    for (u16 i = 0; i < MAX_ACTIVE_NOTES; i++) {
        if (active_notes[i].active && !active_notes[i].hit && active_notes[i].lane == lane) {
            s16 y_diff = abs(active_notes[i].y - HIT_ZONE_Y);
            if (y_diff < min_y_diff) {
                min_y_diff = y_diff;
                closest_idx = i;
            }
        }
    }

    if (closest_idx == -1) return;  // No note in this lane

    u16 frame_diff = min_y_diff / NOTE_SPEED;

    if (frame_diff <= HIT_WINDOW_PERFECT) {
        // ── PERFECT HIT ──
        active_notes[closest_idx].hit = TRUE;
        game_score.perfect_count++;
        game_score.combo++;
        if (game_score.combo > game_score.max_combo)
            game_score.max_combo = game_score.combo;

        // Combo gauge fill (Gold note hit adds 20%)
        if (!game_score.combo_active && active_notes[closest_idx].gold) {
            game_score.combo_gauge += 20;
            if (game_score.combo_gauge > COMBO_GAUGE_MAX)
                game_score.combo_gauge = COMBO_GAUGE_MAX;
        }

        // Decrement combo bonus notes counter if active
        if (game_score.combo_active) {
            game_score.combo_timer--;
            game_score.combo_gauge = game_score.combo_timer * 10;
            if (game_score.combo_timer == 0) {
                game_score.combo_active = FALSE;
            }
        }

        // Score: Perfect hit gets full base_note_value * multiplier
        u32 points = base_note_value * getGlobalMultiplier();
        game_score.score += points;

        // Visual feedback text
        VDP_drawText("PERFECT!", 1, 27);
        drawHUD();

        // Release note sprite
        if (note_sprites[closest_idx] != NULL) {
            SPR_releaseSprite(note_sprites[closest_idx]);
            note_sprites[closest_idx] = NULL;
        }

        // Flash hitzone
        if (hitzone_sprites[lane] != NULL) {
            SPR_setAnimAndFrame(hitzone_sprites[lane], 0, 1);
            hitzone_flash_timer[lane] = 8;
        }

        // Spawn explosion effect at hit position!
        spawnExplosion(play_lane_x[lane], HIT_ZONE_Y);

    } else if (frame_diff <= HIT_WINDOW_GOOD) {
        // ── GOOD HIT ──
        active_notes[closest_idx].hit = TRUE;
        game_score.good_count++;
        game_score.combo++;
        if (game_score.combo > game_score.max_combo)
            game_score.max_combo = game_score.combo;

        // Combo gauge fill (Gold note hit adds 20%)
        if (!game_score.combo_active && active_notes[closest_idx].gold) {
            game_score.combo_gauge += 20;
            if (game_score.combo_gauge > COMBO_GAUGE_MAX)
                game_score.combo_gauge = COMBO_GAUGE_MAX;
        }

        // Decrement combo bonus notes counter if active
        if (game_score.combo_active) {
            game_score.combo_timer--;
            game_score.combo_gauge = game_score.combo_timer * 10;
            if (game_score.combo_timer == 0) {
                game_score.combo_active = FALSE;
            }
        }

        // Score: Good hit gets 50% base_note_value * multiplier
        u32 points = (base_note_value / 2) * getGlobalMultiplier();
        game_score.score += points;

        VDP_drawText("GOOD!   ", 1, 27);
        drawHUD();

        if (note_sprites[closest_idx] != NULL) {
            SPR_releaseSprite(note_sprites[closest_idx]);
            note_sprites[closest_idx] = NULL;
        }

        // Flash hitzone
        if (hitzone_sprites[lane] != NULL) {
            SPR_setAnimAndFrame(hitzone_sprites[lane], 0, 1);
            hitzone_flash_timer[lane] = 6;
        }

        // Spawn smaller explosion for good hits too
        spawnExplosion(play_lane_x[lane], HIT_ZONE_Y);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// EXPLOSION EFFECTS
// ─────────────────────────────────────────────────────────────────────────────

void spawnExplosion(s16 x, s16 y) {
    for (u16 i = 0; i < MAX_EXPLOSIONS; i++) {
        if (!explosions[i].active) {
            explosions[i].active = TRUE;
            explosions[i].x = x;
            explosions[i].y = y;
            explosions[i].frame_idx = 0;
            explosions[i].timer = EXPLOSION_FRAME_DURATION;

            explosion_sprites[i] = SPR_addSprite(&spr_explosion, x, y, TILE_ATTR(PAL3, TRUE, FALSE, FALSE));
            if (explosion_sprites[i] != NULL) {
                SPR_setAnimAndFrame(explosion_sprites[i], 0, 0);
                SPR_setVisibility(explosion_sprites[i], VISIBLE);
            }
            return;
        }
    }
}

void updateExplosions() {
    for (u16 i = 0; i < MAX_EXPLOSIONS; i++) {
        if (explosions[i].active) {
            explosions[i].timer--;

            if (explosions[i].timer == 0) {
                explosions[i].frame_idx++;

                if (explosions[i].frame_idx >= EXPLOSION_TOTAL_FRAMES) {
                    // Animation complete — remove
                    explosions[i].active = FALSE;
                    if (explosion_sprites[i] != NULL) {
                        SPR_releaseSprite(explosion_sprites[i]);
                        explosion_sprites[i] = NULL;
                    }
                } else {
                    // Advance to next frame
                    explosions[i].timer = EXPLOSION_FRAME_DURATION;
                    if (explosion_sprites[i] != NULL) {
                        SPR_setAnimAndFrame(explosion_sprites[i], 0, explosions[i].frame_idx);
                    }
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// JOYPAD HANDLER
// ─────────────────────────────────────────────────────────────────────────────

void joyHandler(u16 joy, u16 changed, u16 state) {
    if (joy != JOY_1) return;

    if (game_state == STATE_TITLE) {
        if (changed & state & BUTTON_START) {
            enterSelect();
        }
    }
    else if (game_state == STATE_SELECT) {
        // Song navigation
        if (changed & state & BUTTON_UP) {
            if (selected_song_idx > 0) selected_song_idx--;
            else selected_song_idx = SONG_COUNT - 1;
        }
        if (changed & state & BUTTON_DOWN) {
            if (selected_song_idx < SONG_COUNT - 1) selected_song_idx++;
            else selected_song_idx = 0;
        }

        // Difficulty
        if (changed & state & BUTTON_LEFT) {
            if (selected_difficulty > 0) selected_difficulty--;
            else selected_difficulty = DIFFICULTY_COUNT - 1;
        }
        if (changed & state & BUTTON_RIGHT) {
            if (selected_difficulty < DIFFICULTY_COUNT - 1) selected_difficulty++;
            else selected_difficulty = 0;
        }

        if (changed & state & BUTTON_START) {
            enterPlay();
        }
    }
    else if (game_state == STATE_PLAY) {
        // Map buttons to lanes and check hits
        // Lane 0=LEFT, 1=UP, 2=DOWN, 3=A, 4=B
        for (u16 i = 0; i < active_lane_count; i++) {
            u8 lane = active_lanes_ptr[i];

            u16 button_mask = 0;
            switch (lane) {
                case LANE_LEFT:  button_mask = BUTTON_LEFT; break;
                case LANE_UP:    button_mask = BUTTON_UP; break;
                case LANE_DOWN:  button_mask = BUTTON_DOWN; break;
                case LANE_A:     button_mask = BUTTON_A; break;
                case LANE_B:     button_mask = BUTTON_B; break;
            }

            // Button pressed → check for hit + visual feedback
            if (changed & state & button_mask) {
                if (gameplay_phase == PHASE_PLAYING) {
                    checkNoteHit(lane);
                }

                // Even if no note was hit, flash the hitzone (button press feedback)
                if (hitzone_sprites[lane] != NULL && hitzone_flash_timer[lane] == 0) {
                    SPR_setAnimAndFrame(hitzone_sprites[lane], 0, 1);
                    hitzone_flash_timer[lane] = 4;  // Short flash for empty press
                }
            }

            // Button released → hitzone returns to idle (if flash timer expired)
            if (changed & ~state & button_mask) {
                if (hitzone_sprites[lane] != NULL && hitzone_flash_timer[lane] == 0) {
                    SPR_setAnimAndFrame(hitzone_sprites[lane], 0, 0);
                }
            }
        }

        // Trigger combo multiplier (RIGHT button when gauge is full)
        if (changed & state & BUTTON_RIGHT) {
            if (gameplay_phase == PHASE_PLAYING && game_score.combo_gauge >= COMBO_GAUGE_MAX && !game_score.combo_active) {
                game_score.combo_active = TRUE;
                game_score.combo_timer = 10; // Active for exactly 10 notes
                game_score.combo_gauge = 100;
                combo_strobe_frame = 0;
                drawHUD();
            }
        }
    }
    else if (game_state == STATE_RESULTS) {
        if (changed & state & BUTTON_START) {
            enterLeaderboard();
        }
    }
    else if (game_state == STATE_LEADERBOARD) {
        if (changed & state & BUTTON_START) {
            enterPostMenu();
        }
    }
    else if (game_state == STATE_POST_MENU) {
        if (changed & state & BUTTON_UP) {
            selected_post_option = (selected_post_option > 0) ? selected_post_option - 1 : 2;
            post_menu_dirty = TRUE;
        }
        if (changed & state & BUTTON_DOWN) {
            selected_post_option = (selected_post_option < 2) ? selected_post_option + 1 : 0;
            post_menu_dirty = TRUE;
        }
        if (changed & state & BUTTON_START) {
            if (selected_post_option == 0) {
                enterPlay(); // Restart song
            } else if (selected_post_option == 1) {
                enterSelect(); // Return to song select
            } else if (selected_post_option == 2) {
                enterTitle(); // Return to title screen
            }
        }
    }
}
