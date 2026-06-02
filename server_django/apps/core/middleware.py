from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import reverse

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Whitelisted paths that do not require authentication
        # We allow login, admin, and static files
        if (
            path == reverse('web:login') or
            path.startswith('/admin/') or
            path.startswith('/static/') or
            path.startswith('/ws/')
        ):
            return self.get_response(request)

        # Check if user is logged in
        if not request.session.get('user_id'):
            if path.startswith('/api/'):
                return JsonResponse({'error': 'Authentication required'}, status=401)
            return redirect('web:login')

        response = self.get_response(request)
        
        # Prevent browser caching for protected pages so Back button forces reload/redirect
        if not path.startswith('/static/'):
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
        return response
