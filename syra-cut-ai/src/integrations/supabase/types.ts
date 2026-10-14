export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      video_assets: {
        Row: {
          created_at: string
          id: string
          job_id: string
          metadata: Json | null
          path: string | null
          type: string
          url: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          job_id: string
          metadata?: Json | null
          path?: string | null
          type: string
          url?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          job_id?: string
          metadata?: Json | null
          path?: string | null
          type?: string
          url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "video_assets_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "video_jobs"
            referencedColumns: ["id"]
          },
        ]
      }
      video_job_events: {
        Row: {
          created_at: string
          event_type: string
          id: string
          job_id: string
          message: string | null
          payload: Json | null
        }
        Insert: {
          created_at?: string
          event_type: string
          id?: string
          job_id: string
          message?: string | null
          payload?: Json | null
        }
        Update: {
          created_at?: string
          event_type?: string
          id?: string
          job_id?: string
          message?: string | null
          payload?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "video_job_events_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "video_jobs"
            referencedColumns: ["id"]
          },
        ]
      }
      video_jobs: {
        Row: {
          ai_plan: Json | null
          created_at: string
          duration_seconds: number | null
          error_message: string | null
          height: number | null
          id: string
          intelligence: Json | null
          intelligence_status: string
          output_file_path: string | null
          output_file_url: string | null
          progress: number
          retry_count: number
          simulated: boolean
          source_file_name: string | null
          source_file_path: string | null
          source_file_size: number | null
          source_file_url: string | null
          status: Database["public"]["Enums"]["video_job_status"]
          technical_report: Json | null
          title_suggestion: string | null
          transcript: string | null
          updated_at: string
          user_id: string
          variants: Json
          virality_score: number | null
          width: number | null
        }
        Insert: {
          ai_plan?: Json | null
          created_at?: string
          duration_seconds?: number | null
          error_message?: string | null
          height?: number | null
          id?: string
          intelligence?: Json | null
          intelligence_status?: string
          output_file_path?: string | null
          output_file_url?: string | null
          progress?: number
          retry_count?: number
          simulated?: boolean
          source_file_name?: string | null
          source_file_path?: string | null
          source_file_size?: number | null
          source_file_url?: string | null
          status?: Database["public"]["Enums"]["video_job_status"]
          technical_report?: Json | null
          title_suggestion?: string | null
          transcript?: string | null
          updated_at?: string
          user_id: string
          variants?: Json
          virality_score?: number | null
          width?: number | null
        }
        Update: {
          ai_plan?: Json | null
          created_at?: string
          duration_seconds?: number | null
          error_message?: string | null
          height?: number | null
          id?: string
          intelligence?: Json | null
          intelligence_status?: string
          output_file_path?: string | null
          output_file_url?: string | null
          progress?: number
          retry_count?: number
          simulated?: boolean
          source_file_name?: string | null
          source_file_path?: string | null
          source_file_size?: number | null
          source_file_url?: string | null
          status?: Database["public"]["Enums"]["video_job_status"]
          technical_report?: Json | null
          title_suggestion?: string | null
          transcript?: string | null
          updated_at?: string
          user_id?: string
          variants?: Json
          virality_score?: number | null
          width?: number | null
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      video_job_status:
        | "UPLOADED"
        | "QUEUED"
        | "PROCESSING"
        | "TRANSCRIBING"
        | "ANALYZING"
        | "CUTTING"
        | "RENDERING"
        | "VALIDATING"
        | "READY_FOR_HUMAN_REVIEW"
        | "FAILED"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      video_job_status: [
        "UPLOADED",
        "QUEUED",
        "PROCESSING",
        "TRANSCRIBING",
        "ANALYZING",
        "CUTTING",
        "RENDERING",
        "VALIDATING",
        "READY_FOR_HUMAN_REVIEW",
        "FAILED",
      ],
    },
  },
} as const
