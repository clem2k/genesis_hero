#ifndef _GAME_H_
#define _GAME_H_

#include <genesis.h>

// Lanes (5 max — RIGHT is reserved for combo activation)
#define LANE_LEFT     0
#define LANE_UP       1
#define LANE_DOWN     2
#define LANE_A        3
#define LANE_B        4
#define NUM_LANES     5

// Gameplay settings
#define NOTE_SPEED          3     // Pixels per frame down the screen
#define HIT_ZONE_Y        184     // Hit zone Y coordinate (moved up for 32px sprites)
#define SPAWN_Y            -32    // Notes start above top of screen
#define HIT_WINDOW_PERFECT  5     // ±5 frames of precision
#define HIT_WINDOW_GOOD    12     // ±12 frames of precision
#define COMBO_GAUGE_MAX   100     // Full gauge = 100
#define COMBO_MULTIPLIER    5     // Combo multiplier (x5)
#define COMBO_DURATION    600     // Duration of x5 multiplier (10 seconds @ 60fps)

// Game states
#define STATE_TITLE       0
#define STATE_SELECT      1
#define STATE_PLAY        2
#define STATE_RESULTS     3
#define STATE_LEADERBOARD 4
#define STATE_POST_MENU   5

// Gameplay phases (for STATE_PLAY countdown)
#define PHASE_COUNTDOWN  0
#define PHASE_PLAYING    1

// PCM Sound IDs for XGM driver (64-255 are reserved for SFX)
#define SFX_1_ID           64
#define SFX_2_ID           65
#define SFX_3_ID           66
#define SFX_INTRO_ID       67
#define SFX_SCORE_0_ID     68
#define SFX_SCORE_1000_ID  69
#define SFX_SCORE_200K_ID  70
#define SFX_SCORE_600K_ID  71
#define SFX_SCORE_900K_ID  72

// Score tracking structure
typedef struct {
    u32 score;
    u16 combo;
    u16 max_combo;
    u16 perfect_count;
    u16 good_count;
    u16 miss_count;
    s16 combo_gauge;       // 0 to 100
    bool combo_active;     // Is x5 active
    u16 combo_timer;       // Frames remaining for x5
} GameScore;

// Active note structure (for notes on screen)
typedef struct {
    s16 y;                 // Y screen position
    u16 note_idx;          // Index in the original song note array
    u8 lane;               // Lane index (0 to 4)
    bool active;           // Is this note slot active on screen
    bool hit;              // Has this note been hit by the player
    bool gold;             // Is this a gold note?
} ActiveNote;

// Explosion effect structure (hit feedback)
typedef struct {
    s16 x;                 // X screen position
    s16 y;                 // Y screen position
    u8 frame_idx;          // Current animation frame (0-3)
    u8 timer;              // Frames until next animation step
    bool active;           // Is this explosion active
} ActiveExplosion;

// Maximum notes visible on screen at any time
#define MAX_ACTIVE_NOTES   24

// Maximum simultaneous explosion effects
#define MAX_EXPLOSIONS      4

// Explosion animation timing (frames per animation step)
#define EXPLOSION_FRAME_DURATION  3
#define EXPLOSION_TOTAL_FRAMES    4

#endif // _GAME_H_
