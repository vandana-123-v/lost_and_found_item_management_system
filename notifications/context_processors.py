def inbox(request):
    if not request.user.is_authenticated:
        return {}
    notes = request.user.notifications.filter(is_read=False)
    return {"unread_count": notes.count(), "inbox_preview": notes[:4]}
