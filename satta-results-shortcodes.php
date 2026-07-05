<?php
/**
 * Plugin Name: Satta Results Shortcodes
 * Description: Display daily Satta results and monthly chart data from JSON files via shortcodes.
 * Version: 1.0.0
 * Author: Satta Scraper
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

function satta_results_fetch_json( $url ) {
    $response = wp_remote_get( esc_url_raw( $url ), array( 'timeout' => 20 ) );
    if ( is_wp_error( $response ) ) {
        return null;
    }

    $body = wp_remote_retrieve_body( $response );
    if ( empty( $body ) ) {
        return null;
    }

    $data = json_decode( $body, true );
    if ( json_last_error() !== JSON_ERROR_NONE ) {
        return null;
    }

    return $data;
}

function satta_results_shortcode( $atts ) {
    $atts = shortcode_atts( array(
        'url' => 'https://patnasattaking.com/satta/results.json',
    ), $atts, 'satta_results' );

    $data = satta_results_fetch_json( $atts['url'] );
    if ( empty( $data ) || empty( $data['games'] ) ) {
        return '<div class="satta-results">Unable to load Satta results.</div>';
    }

    $html  = '<div class="satta-results">';
    $html .= '<h2>Satta Results</h2>';

    foreach ( $data['games'] as $game ) {
        $game_name      = isset( $game['game-name'] ) ? sanitize_text_field( $game['game-name'] ) : '';
        $game_time      = isset( $game['game-time'] ) ? sanitize_text_field( $game['game-time'] ) : '';
        $yesterday      = isset( $game['yesterday-number'] ) ? sanitize_text_field( $game['yesterday-number'] ) : '';
        $today          = isset( $game['today-number'] ) ? sanitize_text_field( $game['today-number'] ) : '';
        $game_link      = isset( $game['game-link'] ) ? esc_url( $game['game-link'] ) : '';

        $html .= '<div class="satta-game">';
        $html .= '<h3>' . esc_html( $game_name ) . '</h3>';
        $html .= '<p><strong>Time:</strong> ' . esc_html( $game_time ) . '</p>';
        $html .= '<p><strong>Yesterday:</strong> ' . esc_html( $yesterday ) . '</p>';
        $html .= '<p><strong>Today:</strong> ' . esc_html( $today ) . '</p>';
        if ( $game_link ) {
            $html .= '<p><a href="' . $game_link . '" target="_blank" rel="noopener noreferrer">View Chart</a></p>';
        }
        $html .= '</div>';
    }

    $html .= '</div>';
    return $html;
}
add_shortcode( 'satta_results', 'satta_results_shortcode' );

function satta_monthly_chart_shortcode( $atts ) {
    $atts = shortcode_atts( array(
        'url'   => 'https://patnasattaking.com/satta/monthly_charts.json',
        'year'  => date( 'Y' ),
        'month' => date( 'F' ),
    ), $atts, 'satta_monthly_chart' );

    $year  = sanitize_text_field( $atts['year'] );
    $month = sanitize_text_field( $atts['month'] );

    $data = satta_results_fetch_json( $atts['url'] );
    if ( empty( $data ) || empty( $data[ $year ] ) || empty( $data[ $year ][ $month ] ) ) {
        return '<div class="satta-chart">No chart data available for ' . esc_html( $month ) . ' ' . esc_html( $year ) . '.</div>';
    }

    $html  = '<div class="satta-chart">';
    $html .= '<h2>' . esc_html( $month ) . ' ' . esc_html( $year ) . ' Satta Chart</h2>';
    $html .= '<table class="satta-chart-table" border="1" cellpadding="6" cellspacing="0">';
    $html .= '<thead><tr><th>Date</th><th>Game</th><th>Result</th></tr></thead>';
    $html .= '<tbody>';

    foreach ( $data[ $year ][ $month ] as $day => $games ) {
        if ( empty( $games ) || ! is_array( $games ) ) {
            continue;
        }

        foreach ( $games as $game_name => $result ) {
            $html .= '<tr>';
            $html .= '<td>' . esc_html( $day ) . '</td>';
            $html .= '<td>' . esc_html( $game_name ) . '</td>';
            $html .= '<td>' . esc_html( $result ) . '</td>';
            $html .= '</tr>';
        }
    }

    $html .= '</tbody>';
    $html .= '</table>';
    $html .= '</div>';
    return $html;
}
add_shortcode( 'satta_monthly_chart', 'satta_monthly_chart_shortcode' );

