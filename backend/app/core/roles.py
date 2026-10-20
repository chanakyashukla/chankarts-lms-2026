from enum import Enum


class UserRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class Permission(str, Enum):
    # Student permissions
    VIEW_OWN_PROFILE = "view_own_profile"
    EDIT_OWN_PROFILE = "edit_own_profile"
    VIEW_OWN_SCHEDULE = "view_own_schedule"
    VIEW_OWN_PROGRESS = "view_own_progress"
    VIEW_OWN_ATTENDANCE = "view_own_attendance"
    SUBMIT_ASSIGNMENT = "submit_assignment"
    TAKE_QUIZ = "take_quiz"
    VIEW_LEARNING_RESOURCES = "view_learning_resources"

    # Parent/Guardian permissions (scoped to linked children only)
    VIEW_LINKED_STUDENTS = "view_linked_students"
    VIEW_LINKED_RECORDS = "view_linked_records"
    VIEW_FAMILY_BILLING = "view_family_billing"
    
    # Instructor permissions
    VIEW_ASSIGNED_STUDENTS = "view_assigned_students"
    MANAGE_CLASS_SCHEDULE = "manage_class_schedule"
    RECORD_ATTENDANCE = "record_attendance"
    ADD_PROGRESS_NOTES = "add_progress_notes"
    CREATE_ASSIGNMENTS = "create_assignments"
    CREATE_QUIZZES = "create_quizzes"
    MANAGE_LEARNING_RESOURCES = "manage_learning_resources"
    VIEW_ALL_STUDENTS = "view_all_students"
    
    # Admin permissions
    MANAGE_USERS = "manage_users"
    MANAGE_INSTRUCTORS = "manage_instructors"
    MANAGE_STUDENTS = "manage_students"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_SYLLABUS = "manage_syllabus"
    MANAGE_EXAMS = "manage_exams"
    MANAGE_CERTIFICATES = "manage_certificates"
    MANAGE_BILLING = "manage_billing"
    SYSTEM_SETTINGS = "system_settings"


ROLE_PERMISSIONS = {
    UserRole.STUDENT: [
        Permission.VIEW_OWN_PROFILE,
        Permission.EDIT_OWN_PROFILE,
        Permission.VIEW_OWN_SCHEDULE,
        Permission.VIEW_OWN_PROGRESS,
        Permission.VIEW_OWN_ATTENDANCE,
        Permission.SUBMIT_ASSIGNMENT,
        Permission.TAKE_QUIZ,
        Permission.VIEW_LEARNING_RESOURCES,
    ],
    UserRole.PARENT: [
        Permission.VIEW_LINKED_STUDENTS,
        Permission.VIEW_LINKED_RECORDS,
        Permission.VIEW_FAMILY_BILLING,
        Permission.VIEW_OWN_PROFILE,
        Permission.EDIT_OWN_PROFILE,
        Permission.VIEW_LEARNING_RESOURCES,
    ],
    UserRole.INSTRUCTOR: [
        Permission.VIEW_ASSIGNED_STUDENTS,
        Permission.MANAGE_CLASS_SCHEDULE,
        Permission.RECORD_ATTENDANCE,
        Permission.ADD_PROGRESS_NOTES,
        Permission.CREATE_ASSIGNMENTS,
        Permission.CREATE_QUIZZES,
        Permission.MANAGE_LEARNING_RESOURCES,
        Permission.VIEW_OWN_PROFILE,
        Permission.EDIT_OWN_PROFILE,
    ],
    UserRole.ADMIN: [
        permission for permission in Permission
    ],
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, [])


def get_role_permissions(role: UserRole) -> list[Permission]:
    return ROLE_PERMISSIONS.get(role, [])
